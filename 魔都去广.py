# coding=utf-8
"""
魔都影视（去广告）爬虫
目标站: 魔都资源 (https://www.mdzyapi.com/api.php/provide/vod/at/xml/)
模板: 影视聚合 / 苹果CMS(XML 采集接口) + 内置去广告清洗
站点类型: 综合影视 (电影/电视剧/动漫/综艺/短剧/AI漫剧/体育/伦理)

分类写法 (参考暴风去广.py):
  - 苹果CMS 的 XML 接口在 ac=list 尾部返回 <class> 扁平分类表, 但顶层 id(7/8/9)
    基本没有数据, 真实内容都挂在子分类 id 上 (电影→10~25, 剧→26~33, 综艺→34~37)
  - 因此按站点真实分类表分组: 每个一级栏目提供 "类型/地区"(子分类 t) + "年份"(year)
  - 年份筛选使用接口原生 year 参数, 真实生效
  - 分类获取失败时回落静态内置分类, 保证壳端分类栏不空白

线路机制:
  - vod_play_from = modum3u8 (统一改名 "魔都高清"), vod_play_url 为 "集名$m3u8直链"
  - 播放时由本地代理清洗 m3u8 广告后交给播放器, parse=0

去广告优化 (保证 TVBox 正常播放):
  - 魔都广告以 #EXT-X-DISCONTINUITY 包裹, 且广告片段指向另一个内容目录(相对路径),
    与正片片段 (同业务主目录) 明显不同
  - 按 DISCONTINUITY 切块 -> 统计全部片段的主目录签名 -> 只保留主流(正片)签名的块,
    删除广告块及其附带的 #EXT-X-KEY:METHOD=NONE
  - 若广告未包裹 DISCONTINUITY, 亦按签名逐片段剔除, 保证正片完整
  - 全部片段/加密 KEY/MAP 的相对地址统一改写为绝对地址, 播放器可直接回源拉流
  - 重算 #EXT-X-TARGETDURATION, 补全 #EXTM3U / #EXT-X-VERSION / #EXT-X-ENDLIST
  - 多码率 master playlist 自动选最高带宽; 任一环节失败自动回退原播放列表
  - 单条覆盖式缓存, 换集/换源自动刷新
  - 无弹幕

支持: 首页, 一/二级分类(含筛选), 搜索, 详情, 播放 (六接口齐全)
"""

import sys
import re
import time
import requests
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlparse, quote, unquote, parse_qs, urlencode, urlunparse

sys.path.append('..')
from base.spider import Spider


class Spider(Spider):
    # ---------- 站点常量 ----------
    SITE_URL = "https://www.mdzyapi.com"
    API = "https://www.mdzyapi.com/api.php/provide/vod/at/xml/"

    # 简介推广信息
    PROMO = (
        "更多优质资源尽在源力\n"
        "微信公众号：源力软件汇\n\n"
    )

    # 一级栏目定义: (展示名, 默认子分类 id, 成员子分类 id 列表, 筛选名)
    # 说明: 站点顶层 id 基本无数据, 每个栏目直接落到成员子分类
    GROUP_DEFS = [
        ("电影", 10, [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25], "类型"),
        ("电视剧", 26, [26, 27, 28, 29, 30, 31, 32, 33], "地区"),
        ("动漫", 1, [1, 2, 3, 4, 5, 6], "类型"),
        ("综艺", 34, [34, 35, 36, 37], "地区"),
        ("短剧", 38, [38], None),
        ("AI漫剧", 42, [42], None),
        ("体育", 40, [40, 41], "类型"),
        ("伦理片", 39, [39], None),
    ]

    # 子分类静态名称 (分类接口异常时兜底, 保证分类栏与筛选器始终完整)
    SUB_NAMES = {
        1: "国产动漫", 2: "日韩动漫", 3: "欧美动漫", 4: "港台动漫", 5: "动漫电影", 6: "里番动漫",
        10: "动作片", 11: "喜剧片", 12: "爱情片", 13: "科幻片", 14: "恐怖片", 15: "剧情片",
        16: "战争片", 17: "惊悚片", 18: "家庭片", 19: "古装片", 20: "历史片", 21: "悬疑片",
        22: "犯罪片", 23: "灾难片", 24: "记录片", 25: "短片",
        26: "国产剧", 27: "香港剧", 28: "韩国剧", 29: "欧美剧", 30: "台湾剧",
        31: "日本剧", 32: "海外剧", 33: "泰国剧",
        34: "大陆综艺", 35: "港台综艺", 36: "日韩综艺", 37: "欧美综艺",
        38: "短剧", 39: "伦理片", 40: "体育", 41: "足球", 42: "AI漫剧",
    }

    def init(self, extend=""):
        self.session = requests.Session()
        self.headers = {
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            ),
            'Accept': 'application/xml, text/xml, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Referer': self.SITE_URL + '/',
        }

        # 年份筛选: 全部 + 近十几年
        cur_year = time.localtime().tm_year
        self.year_options = [("全部", "")] + [
            (str(y), str(y)) for y in range(cur_year + 1, 2014, -1)
        ]

        # 分类缓存
        self._type_name = {}          # type_id -> 站点分类名
        self._class_list = None       # 首页 class
        self._filters_map = None      # 一级栏目 -> 筛选器定义

        # ---------- 去广告清洗缓存 (单条目, 覆盖式) ----------
        self.cached_url = None
        self.cached_content = None

    def getName(self):
        return "魔都去广"

    # ==================== 基础请求 ====================

    def _api_text(self, params, timeout=20, tries=3):
        """调用 XML 采集接口, 返回解码后的文本 (失败返回 "")"""
        for _ in range(tries):
            try:
                resp = self.session.get(
                    self.API, params=params, headers=self.headers,
                    timeout=timeout, verify=False
                )
                if resp.status_code == 200 and resp.content:
                    return resp.content.decode('utf-8', 'ignore')
            except Exception:
                time.sleep(1)
        return ""

    @staticmethod
    def _read_list_meta(root):
        node = root.find('list')
        if node is None:
            return {}, []
        meta = {
            "page": int(node.get("page", 1) or 1),
            "pagecount": int(node.get("pagecount", 0) or 0),
            "limit": int(node.get("pagesize", 20) or 20),
            "total": int(node.get("recordcount", 0) or 0),
        }
        return meta, list(node.findall('video'))

    @staticmethod
    def _txt(node, tag):
        el = node.find(tag)
        if el is None:
            return ""
        return (el.text or "").strip()

    def _fetch_text(self, url, timeout=20):
        """抓取文本 (m3u8 等), 带默认请求头"""
        try:
            resp = self.session.get(url, headers=self.headers, timeout=timeout, verify=False)
            if resp.status_code == 200 and resp.text:
                return resp.text
        except Exception:
            pass
        return None

    # ==================== 分类 (动态获取全部分类) ====================

    def _load_classes(self):
        if self._class_list is not None:
            return
        text = self._api_text({"ac": "list"})
        m = re.search(r"<class>(.*?)</class>", text, re.S)
        if m:
            for cid, name in re.findall(r'<ty id="(\d+)">(.*?)</ty>', m.group(1)):
                if name:
                    self._type_name[cid] = name

        class_list = []
        filters_map = {}
        for display, default_tid, member_ids, filter_name in self.GROUP_DEFS:
            # 优先用站点分类名, 接口异常时用静态名称, 保证分类条目不缺失
            members = [
                (str(t), self._type_name.get(str(t)) or self.SUB_NAMES.get(t) or str(t))
                for t in member_ids
            ]

            class_list.append({"type_id": str(default_tid), "type_name": display})

            filters = []
            if filter_name and len(members) > 1:
                # 默认子分类排到首位, 与 categoryContent 的默认取值保持一致
                ordered = sorted(members, key=lambda x: 0 if x[0] == str(default_tid) else 1)
                filters.append({
                    "key": "t",
                    "name": filter_name,
                    "value": [{"n": n, "v": t} for t, n in ordered],
                })
            filters.append(self._year_filter())
            filters_map[str(default_tid)] = filters

        self._class_list = class_list
        self._filters_map = filters_map

    def _year_filter(self):
        return {
            "key": "year",
            "name": "年份",
            "value": [{"n": n, "v": v} for n, v in self.year_options],
        }

    # ==================== 卡片解析 ====================

    def _parse_item(self, v):
        return {
            "vod_id": self._txt(v, "id"),
            "vod_name": self._txt(v, "name"),
            "vod_pic": self._txt(v, "pic"),
            "vod_remarks": self._txt(v, "note"),
            "vod_year": self._txt(v, "year"),
            "vod_area": self._txt(v, "area"),
            "vod_type": self._txt(v, "type"),
        }

    # ==================== 首页 ====================

    def homeContent(self, filter):
        self._load_classes()
        return {
            "class": [dict(c) for c in self._class_list],
            "filters": {k: [dict(f) for f in v] for k, v in self._filters_map.items()},
            "list": [],
        }

    def homeVideoContent(self):
        """首页推荐: 最新入库"""
        text = self._api_text({"ac": "list", "pg": "1"})
        try:
            root = ET.fromstring(text)
        except Exception:
            return {"list": []}
        _, videos = self._read_list_meta(root)
        return {"list": [self._parse_item(v) for v in videos]}

    # ==================== 分类(含筛选) ====================

    def categoryContent(self, tid, pg, filter, extend):
        self._load_classes()
        page = int(pg) if pg else 1
        extend = extend or {}

        # 子分类 (类型/地区): 未选择时用默认的 tid
        t = str(extend.get("t") or tid or "").strip()
        params = {"ac": "list", "t": t, "pg": str(page)}

        # 年份: 站点原生支持, 真实生效
        year = str(extend.get("year") or "").strip()
        if year and year != "全部":
            params["year"] = year

        text = self._api_text(params)
        try:
            root = ET.fromstring(text)
        except Exception:
            return {"list": [], "page": page, "pagecount": 0, "limit": 20, "total": 0}

        meta, videos = self._read_list_meta(root)
        meta["list"] = [self._parse_item(v) for v in videos]
        return meta

    # ==================== 搜索 ====================

    def searchContent(self, key, quick, pg="1"):
        keyword = (key or "").strip()
        if not keyword:
            return {"list": [], "page": 1, "pagecount": 0, "limit": 20, "total": 0}
        text = self._api_text({"ac": "detail", "wd": keyword, "pg": str(pg or "1")})
        try:
            root = ET.fromstring(text)
        except Exception:
            return {"list": [], "page": int(pg or 1), "pagecount": 0, "limit": 20, "total": 0}
        meta, videos = self._read_list_meta(root)
        meta["list"] = [self._parse_item(v) for v in videos]
        return meta

    # ==================== 详情 ====================

    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vid = ids[0]
        text = self._api_text({"ac": "detail", "ids": vid})
        try:
            root = ET.fromstring(text)
        except Exception:
            return {"list": []}
        videos = list(root.iter('video'))
        if not videos:
            return {"list": []}
        v = videos[0]

        content = self._txt(v, "des") or ""
        content = re.sub(r"<[^>]+>", "", content).strip()
        content = self.PROMO + content

        # 播放源: 每个 <dd flag="xxx"> 为一个源
        play_from = []
        play_url = []
        for dd in v.findall("./dl/dd"):
            flag = dd.get("flag") or "modum3u8"
            data = (dd.text or "").strip()
            if not data:
                continue
            play_from.append(self._pretty_source(flag))
            play_url.append(data)
        if not play_from:
            play_from = ["魔都高清"]

        result = {
            "vod_id": vid,
            "vod_name": self._txt(v, "name"),
            "vod_pic": self._txt(v, "pic"),
            "vod_content": content,
            "vod_actor": self._txt(v, "actor"),
            "vod_director": self._txt(v, "director"),
            "vod_year": self._txt(v, "year"),
            "vod_area": self._txt(v, "area"),
            "vod_type": self._txt(v, "type"),
            "vod_remarks": self._txt(v, "note"),
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url": "$$$".join(play_url),
        }
        return {"list": [result]}

    @staticmethod
    def _pretty_source(name):
        if name.strip().lower() in ("modum3u8", "modu", "魔都"):
            return "魔都高清"
        return name

    # ==================== 播放与代理 (内置去广告) ====================

    def playerContent(self, flag, id, vipFlags=None):
        url = (id or "").strip()
        if not url:
            return {"parse": 1, "url": url, "header": self.headers}

        # m3u8 走本地代理清洗广告; mp4 等直链直接返回
        if "m3u8" in url.lower() and url.lower().startswith(("http://", "https://")):
            proxy_url = self._proxy_base() + "&action=clean&src=" + quote(url, safe="")
            return {"parse": 0, "url": proxy_url, "header": {}}
        return {"parse": 0, "url": url, "header": {}}

    def _proxy_base(self):
        try:
            return self.getProxyUrl(local=True)
        except TypeError:
            return self.getProxyUrl()
        except Exception:
            return self.getProxyUrl()

    # ---------- URL 规范化 (提高缓存命中) ----------

    @staticmethod
    def _normalize_url(url):
        try:
            parsed = urlparse(url)
            q = parse_qs(parsed.query)
            for p in ('_', 't', 'timestamp', 'rand', 'v', 'cb', 'callback'):
                q.pop(p, None)
            return urlunparse(parsed._replace(query=urlencode(q, doseq=True)))
        except Exception:
            return url

    @staticmethod
    def _proxy_headers():
        return {
            'Access-Control-Allow-Origin': '*',
            'Cache-Control': 'no-cache, no-store',
        }

    # ---------- 去广告清洗引擎 ----------

    def _rewrite_uri(self, line, base_url):
        """将任意 URI="..." (KEY / MAP 等) 的相对地址改写为绝对地址"""
        if "URI=" not in line:
            return line

        def repl(m):
            uri = m.group(1)
            if uri and not uri.lower().startswith(("http://", "https://")):
                uri = urljoin(base_url, uri)
            return 'URI="%s"' % uri

        return re.sub(r'URI="([^"]+)"', repl, line)

    @staticmethod
    def _seg_duration(extinf):
        try:
            return float(extinf.split(":", 1)[1].split(",")[0])
        except Exception:
            return 0.0

    @staticmethod
    def _signature(uri, base_url):
        """片段主目录签名: 主机 + 前两级路径 (广告与正片通常位于不同内容目录)"""
        try:
            full = urljoin(base_url, uri)
            p = urlparse(full)
            parts = [x for x in p.path.split("/") if x]
            return p.netloc + "/" + "/".join(parts[:2])
        except Exception:
            return ""

    def _clean_m3u8(self, content, base_url):
        """删除魔都广告块

        魔都广告以 #EXT-X-DISCONTINUITY 包裹, 广告片段指向另一个内容目录(相对路径),
        与正片片段(同业务主目录)签名不同。做法:
          1) 按 DISCONTINUITY 切块, 解析每块片段
          2) 统计全部片段的主目录签名, 取占比 >= 50% 的签名作为正片签名
          3) 只保留含正片签名的块, 删除纯广告块及其附带的 #EXT-X-KEY
          4) 混合块内亦逐片段剔除广告片段
        返回清洗后的播放列表; 无法处理时返回 None (由调用方回退原始内容)。
        """
        if not content:
            return None
        lines = [l.strip() for l in content.splitlines() if l.strip()]
        if not lines:
            return None

        # 1) 拆出 header (媒体片段之前) 与 footer (#EXT-X-ENDLIST)
        header = []
        i = 0
        while i < len(lines):
            s = lines[i]
            if s.startswith("#EXTINF") or s == "#EXT-X-DISCONTINUITY" or not s.startswith("#"):
                break
            header.append(s)
            i += 1

        footer = []
        j = len(lines) - 1
        while j >= i:
            s = lines[j]
            if s == "#EXT-X-ENDLIST":
                footer.insert(0, s)
                j -= 1
            else:
                break

        body = lines[i:j + 1]

        # 2) 按 DISCONTINUITY 切块
        blocks, cur = [], []
        for s in body:
            if s == "#EXT-X-DISCONTINUITY":
                blocks.append(cur)
                cur = []
            else:
                cur.append(s)
        blocks.append(cur)

        # 3) 解析每块为 (片段列表, 其它标签)
        parsed = []
        for b in blocks:
            segs, extras, k = [], [], 0
            while k < len(b):
                s = b[k]
                if s.startswith("#EXTINF"):
                    if k + 1 < len(b) and not b[k + 1].startswith("#"):
                        segs.append((s, b[k + 1]))
                        k += 2
                        continue
                    k += 1
                    continue
                if s.startswith("#"):
                    extras.append(s)
                k += 1
            parsed.append({"segs": segs, "extras": extras})

        # 4) 统计主目录签名, 确定正片签名
        counts = {}
        total_segs = 0
        for blk in parsed:
            for _, uri in blk["segs"]:
                sig = self._signature(uri, base_url)
                counts[sig] = counts.get(sig, 0) + 1
                total_segs += 1
        if total_segs == 0:
            return None
        dominant = max(counts, key=counts.get)
        dominant_ratio = counts.get(dominant, 0) / float(total_segs)

        # 5) 重建: 只保留正片, 清理多余 DISCONTINUITY, 统一改写绝对地址
        out_body = []
        maxdur = 0.0
        segment_count = 0
        first_kept = False

        for blk in parsed:
            if not blk["segs"] and not blk["extras"]:
                continue

            real_segs = blk["segs"]
            if dominant_ratio >= 0.5 and len(counts) > 1:
                real_segs = [(e, u) for e, u in blk["segs"]
                             if self._signature(u, base_url) == dominant]

            # 纯广告块 (有片段但无正片片段) -> 整块丢弃, 含其 KEY 标签
            if blk["segs"] and not real_segs:
                continue

            if first_kept:
                out_body.append("#EXT-X-DISCONTINUITY")

            for e in blk["extras"]:
                out_body.append(self._rewrite_uri(e, base_url))
            for extinf, uri in real_segs:
                d = self._seg_duration(extinf)
                if d > maxdur:
                    maxdur = d
                segment_count += 1
                if not uri.lower().startswith(("http://", "https://")):
                    uri = urljoin(base_url, uri)
                out_body.append(extinf)
                out_body.append(uri)
            first_kept = True

        # 6) 无有效正片片段则不处理, 回退原始
        if segment_count == 0:
            return None

        # 7) 组装 header / TARGETDURATION / body / footer
        out = []
        for h in header:
            if h.startswith("#EXT-X-TARGETDURATION"):
                continue
            out.append(self._rewrite_uri(h, base_url))
        if not any(x.startswith("#EXTM3U") for x in out):
            out.insert(0, "#EXTM3U")
        if not any(x.startswith("#EXT-X-VERSION") for x in out):
            out.append("#EXT-X-VERSION:3")
        out.append("#EXT-X-TARGETDURATION:%d" % max(1, int(maxdur + 0.999)))
        out.extend(out_body)
        out.extend(footer if footer else ["#EXT-X-ENDLIST"])
        return "\n".join(out) + "\n"

    @staticmethod
    def _pick_variant(content, base_url):
        """多码率 master playlist: 选最高带宽 variant"""
        lines = [l.strip() for l in content.splitlines() if l.strip()]
        best, best_bw = None, -1
        for i, l in enumerate(lines):
            if not l.startswith("#EXT-X-STREAM-INF"):
                continue
            m = re.search(r'BANDWIDTH=(\d+)', l)
            bw = int(m.group(1)) if m else 0
            for j in range(i + 1, len(lines)):
                if not lines[j].startswith("#"):
                    if bw >= best_bw:
                        best, best_bw = urljoin(base_url, lines[j]), bw
                    break
        return best

    # ---------- 本地代理 ----------

    def localProxy(self, param):
        if param.get("action") != "clean":
            return [404, "text/plain", "not found"]

        src = param.get("src", "") or ""
        if not src.lower().startswith(("http://", "https://")):
            src = unquote(src)
        if not src.lower().startswith(("http://", "https://")):
            return [400, "text/plain", "缺少有效的 src 参数"]

        norm_url = self._normalize_url(src)

        # 命中缓存
        if self.cached_url == norm_url and self.cached_content is not None:
            return [200, "application/vnd.apple.mpegurl", self.cached_content, self._proxy_headers()]

        try:
            content = self._fetch_text(src)
            if not content:
                return [500, "text/plain", "获取 m3u8 失败"]

            base_url = src.rsplit("/", 1)[0] + "/"

            # 多码率变体: 自动选择最高带宽
            hops = 0
            while "#EXT-X-STREAM-INF" in content and hops < 3:
                variant = self._pick_variant(content, base_url)
                if not variant:
                    break
                sub = self._fetch_text(variant)
                if not sub:
                    break
                content = sub
                base_url = variant.rsplit("/", 1)[0] + "/"
                hops += 1

            cleaned = self._clean_m3u8(content, base_url)
            if not cleaned:
                # 清洗失败/无有效片段 -> 回退原始播放列表, 保证可播
                cleaned = content

            # 覆盖缓存
            self.cached_url = norm_url
            self.cached_content = cleaned

            return [200, "application/vnd.apple.mpegurl", cleaned, self._proxy_headers()]
        except Exception as e:
            return [500, "text/plain", "清洗失败: %s" % e]

    # ==================== 框架接口 ====================

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def destroy(self):
        pass
