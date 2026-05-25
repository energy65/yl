#!/usr/bin/python
# -*- coding: utf-8 -*-
import json, re, urllib.parse
import requests
from lxml import etree
from base.spider import Spider

class Spider(Spider):
    def getName(self): return "追光影视"
    def init(self, extend=""):
        self.name = "追光影视"
        self.host = "https://www.4kmovie.top"
        self.limit = 24
        self.header = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Referer": self.host + "/", "Accept-Language": "zh-CN,zh;q=0.9"}
        self.classes = [{"type_id": "20", "type_name": "电影"}, {"type_id": "37", "type_name": "连续剧"}, {"type_id": "43", "type_name": "动漫"}, {"type_id": "45", "type_name": "综艺"}, {"type_id": "47", "type_name": "B站"}]
        self.filters = {c["type_id"]: [{"key": "area", "name": "地区", "value": [{"n": n, "v": v} for n, v in [("全部", ""), ("大陆", "大陆"), ("香港", "香港"), ("台湾", "台湾"), ("美国", "美国"), ("日本", "日本"), ("韩国", "韩国"), ("英国", "英国")]]}, {"key": "year", "name": "年份", "value": [{"n": "全部", "v": ""}] + [{"n": str(y), "v": str(y)} for y in range(2026, 2015, -1)]}, {"key": "by", "name": "排序", "value": [{"n": "最新", "v": "time"}, {"n": "最热", "v": "hits"}, {"n": "评分", "v": "score"}]}] for c in self.classes}

    def _get(self, url):
        try:
            r = requests.get(url, headers=self.header, timeout=15); r.encoding = r.apparent_encoding or "utf-8"; return r.text
        except Exception as e:
            print(f"[{self.name}] 错误: 请求失败 - {e}"); return ""

    def _fix(self, url): return "https:" + url if url and url.startswith("//") else self.host + url if url and url.startswith("/") else url or ""
    def _txt(self, arr): return re.sub(r"\s+", " ", "".join(arr).strip())

    def _vod_id(self, href):
        m = re.search(r"/vod(?:detail|play)/(\d+)(?:-|\.html)", href or "") or re.search(r"/index\.php/vod/(?:detail|play)/id/(\d+)", href or "")
        return m.group(1) if m else ""

    def _parse_list(self, text):
        html = etree.HTML(text or "")
        if html is None: return []
        items = html.xpath('//a[contains(@class,"module-poster-item") and (contains(@href,"/vodplay/") or contains(@href,"/voddetail/"))]') or html.xpath('//div[contains(@class,"module-items")]//a[(contains(@href,"/vodplay/") or contains(@href,"/voddetail/")) and .//img]') or html.xpath('//a[(contains(@href,"/vodplay/") or contains(@href,"/voddetail/")) and .//img]')
        print(f"[{self.name}] 列表选择器匹配到 {len(items)} 个视频")
        data, seen = [], set()
        for item in items:
            try:
                href = item.get("href", ""); vod_id = self._vod_id(href)
                if not vod_id or vod_id in seen: continue
                seen.add(vod_id)
                img = item.xpath('.//img')
                pic = self._fix((img[0].get("data-original") or img[0].get("data-src") or img[0].get("src") or "") if img else "")
                name = item.get("title") or self._txt(item.xpath('.//*[contains(@class,"module-poster-item-title")]/text()')) or (img[0].get("alt") if img else "") or self._txt(item.xpath('.//text()'))
                remark = self._txt(item.xpath('.//*[contains(@class,"module-item-note")]/text()'))
                data.append({"vod_id": vod_id, "vod_name": name, "vod_pic": pic, "vod_remarks": remark})
            except Exception as e:
                print(f"[{self.name}] 错误: 单条列表解析失败 - {e}"); continue
        return data

    def homeContent(self, filter):
        try: return {"class": self.classes, "filters": self.filters, "list": self._parse_list(self._get(self.host + "/"))}
        except Exception as e:
            print(f"[{self.name}] 错误: 首页内容失败 - {e}"); return {"class": self.classes, "filters": self.filters, "list": []}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            pg = int(pg or 1); area = urllib.parse.quote((extend or {}).get("area", "")); year = (extend or {}).get("year", ""); by = (extend or {}).get("by", "time")
            urls = [f"{self.host}/vodshow/{tid}-{area}--{by}------{pg}---{year}.html", f"{self.host}/vodtype/{tid}.html" if pg == 1 and not area and not year else ""]
            data = []
            for url in [u for u in urls if u]:
                data = self._parse_list(self._get(url))
                if data: break
            return {"list": data, "page": pg, "pagecount": pg + 1 if data else pg, "limit": self.limit, "total": 999 if data else 0}
        except Exception as e:
            print(f"[{self.name}] 错误: 分类爬取失败 - {e}"); return {"list": [], "page": int(pg or 1), "pagecount": 1, "limit": self.limit, "total": 0}

    def detailContent(self, ids):
        result = {"list": []}
        for vod_id in (ids if isinstance(ids, list) else str(ids).split(","))[:1]:
            try:
                html = self._get(f"{self.host}/voddetail/{vod_id}.html") or self._get(f"{self.host}/vodplay/{vod_id}-1-1.html")
                tree = etree.HTML(html or "")
                if tree is None: continue
                name = self._txt(tree.xpath('//h1/text()'))
                pic = self._fix("".join(tree.xpath('(//img[contains(@class,"lazy") or contains(@class,"lazyload")]/@data-original | //img[contains(@class,"lazy") or contains(@class,"lazyload")]/@data-src | //*[contains(@class,"module-info-poster")]//img/@src)[1]')))
                content = self._txt(tree.xpath('//*[contains(@class,"module-info-introduction")]//text() | //*[contains(@class,"vod_content")]//text()'))
                lists = tree.xpath('//div[contains(@class,"module-list") and contains(@class,"tab-list")][.//a[contains(@href,"/vodplay/") or contains(@href,"/index.php/vod/play")]]')
                play_from, play_url, seen_source = [], [], set()
                for i, box in enumerate(lists):
                    source = self._txt(tree.xpath('//*[contains(@class,"module-tab-item")]//text()')) or f"线路{i + 1}"
                    if source in seen_source: continue
                    eps = []
                    for a in box.xpath('.//a[contains(@class,"module-play-list-link") and contains(@href,"/vodplay/")]'):
                        title = self._txt(a.xpath('.//text()')) or a.get("title", "") or f"第{len(eps) + 1}集"; href = self._fix(a.get("href", ""))
                        if href: eps.append(f"{title}${href}")
                    if eps:
                        seen_source.add(source); play_from.append(source); play_url.append("#".join(eps))
                if not play_url:
                    eps = [f"播放{idx + 1}${self._fix(a.get('href', ''))}" for idx, a in enumerate(tree.xpath('//a[contains(@class,"module-play-list-link") and contains(@href,"/vodplay/")]')) if a.get('href')]
                    if eps: play_from.append("默认线路"); play_url.append("#".join(eps))
                if not play_url:
                    play_from.append("默认线路"); play_url.append(f"播放${self.host}/vodplay/{vod_id}-1-1.html")
                print(f"[{self.name}] 详情页提取到 {len(play_from)} 个播放源")
                result["list"].append({"vod_id": vod_id, "vod_name": name, "vod_pic": pic, "vod_content": content, "vod_play_from": "$$$".join(play_from), "vod_play_url": "$$$".join(play_url)})
            except Exception as e:
                print(f"[{self.name}] 错误: 详情解析失败 - {e}"); continue
        return result

    def searchContent(self, key, quick, pg="1"):
        try:
            pg = int(pg or 1); q = urllib.parse.quote(key)
            data = self._parse_list(self._get(f"{self.host}/vodsearch/{q}----------{pg}---.html" if pg > 1 else f"{self.host}/vodsearch/{q}-------------.html"))
            print(f"[{self.name}] 搜索结果数量 {len(data)}")
            return {"list": data, "page": pg, "pagecount": pg + 1 if data else pg, "limit": self.limit, "total": 999 if data else 0}
        except Exception as e:
            print(f"[{self.name}] 错误: 搜索失败 - {e}"); return {"list": [], "page": int(pg or 1), "pagecount": 1}

    def playerContent(self, flag, id, vipFlags):
        try:
            url = self._fix(id)
            if re.search(r"\.(m3u8|mp4|flv)(\?|$)", url): return {"parse": 0, "playUrl": "", "url": url, "header": json.dumps(self.header)}
            print(f"[{self.name}] 播放解析: {flag} -> {url[:50]}...")
            return {"parse": 1, "playUrl": "", "url": url, "header": self.header}
        except Exception as e:
            print(f"[{self.name}] 错误: 播放解析失败 - {e}"); return {"parse": 1, "playUrl": "", "url": id, "header": self.header}
