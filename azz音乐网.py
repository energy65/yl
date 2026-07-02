import re
import sys
from base64 import b64encode, b64decode
from urllib.parse import quote, unquote
from pyquery import PyQuery as pq
from requests import Session, adapters
from urllib3.util.retry import Retry
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.append('..')
from base.spider import Spider

class Spider(Spider):
    def init(self, extend=""):
        self.host = "http://www.aaz.cx"
        self.session = Session()
        adapter = adapters.HTTPAdapter(max_retries=Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504]), pool_connections=20, pool_maxsize=50)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self.headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        self.session.headers.update(self.headers)
        self._verified = False
        self._verify_attempts = 0

    def getName(self): return "AAZ音乐网"
    def isVideoFormat(self, url): return bool(re.search(r'\.(m3u8|mp4|mp3|m4a|flv|aac|wma)(\?|$)', url or "", re.I))
    def manualVideoCheck(self): return False
    def destroy(self): self.session.close()

    def homeContent(self, filter):
        classes = [{"type_name": n, "type_id": i} for n, i in [
            ("歌手", "/singerlist/index/index/index/index.html"),
            ("歌单", "/playtype/index.html"),
            ("专辑", "/albumlist/index.html"),
        ]]
        filters = {}
        try:
            filters = {p: d for p in [c["type_id"] for c in classes if "singer" not in c["type_id"]] if (d := self._fetch_filters(p))}
        except:
            pass
        
        filters["/singerlist/index/index/index/index.html"] = [
            {"key": "area", "name": "地区", "value": [{"n": n, "v": v} for n,v in [("全部","index"),("华语","huayu"),("欧美","oumei"),("韩国","hanguo"),("日本","ribrn")]]},
            {"key": "sex", "name": "性别", "value": [{"n": n, "v": v} for n,v in [("全部","index"),("男","male"),("女","girl"),("组合","band")]]},
            {"key": "genre", "name": "流派", "value": [{"n": n, "v": v} for n,v in [("全部","index"),("流行","liuxing"),("电子","dianzi"),("摇滚","yaogun"),("嘻哈","xiha"),("R&B","rb"),("民谣","minyao"),("爵士","jueshi"),("古典","gudian")]]},
            {"key": "char", "name": "字母", "value": [{"n": n, "v": v} for n,v in [("全部","index")] + [{"n": chr(i), "v": chr(i).lower()} for i in range(65, 91)]]}
        ]
        return {"class": classes, "filters": filters, "list": []}

    def homeVideoContent(self): return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg or 1)
        url = tid
        try:
            if "/singerlist/" in tid:
                p = tid.split('/')
                if len(p) >= 6:
                    url = "/".join(p[:2] + [extend.get(k, p[i]) for i, k in enumerate(["area", "sex", "genre"], 2)] + [f"{extend.get('char', 'index')}.html"])
            elif "id" in extend and extend["id"] not in ["index", "top"]:
                url = tid.replace("index.html", f"{extend['id']}.html").replace("top.html", f"{extend['id']}.html")
                if url == tid: url = f"{tid.rsplit('/', 1)[0]}/{extend['id']}.html"

            if pg > 1:
                sep = "/" if any(x in url for x in ["/singerlist/", "/mvlist/", "/playtype/", "/list/", "/albumlist/"]) else "_"
                url = re.sub(r'(_\d+|/\d+)?\.html$', f'{sep}{pg}.html', url)
        except:
            pass
        
        doc = self.getpq(url)
        
        selectors = [
            ".play_list.mt li",
            ".play_list li", 
            ".singer_list li",
            ".video_list li",
            ".video_list .play li",
            "ul.play li",
            "div.list li",
            ".song_list li",
            ".music_list li",
            ".lkmusic_list li",
        ]
        
        items = None
        for sel in selectors:
            temp = doc(sel)
            if temp and temp.length > 0:
                has_valid = False
                for li in temp.items():
                    a = li("a").eq(0)
                    href = a.attr("href") or ""
                    if re.search(r'/(m|s|p|a|v)/', href):
                        has_valid = True
                        break
                if has_valid:
                    items = temp
                    break
        
        if items is None:
            for sel in selectors:
                temp = doc(sel)
                if temp and temp.length > 0:
                    items = temp
                    break
        
        if items is None:
            items = doc("li")
        
        result = self._parse_list(items, tid)
        return {"list": result, "page": pg, "pagecount": 9999, "limit": 90, "total": 999999}

    def searchContent(self, key, quick, pg="1"):
        doc = self.getpq(f"/so/{quote(key)}/{pg}.html")
        items = doc(".play_list li, .play_list.mt li, .lkmusic_list li, .base_l li, .sovd li")
        result = self._parse_list(items, "search")
        return {"list": result, "page": int(pg)}

    def detailContent(self, ids):
        url = self._abs(ids[0])
        doc = self.getpq(url)
        
        is_singer = "/s/" in url
        is_playlist = "/p/" in url
        is_album = "/a/" in url
        is_mv = "/v/" in url
        is_list_page = is_singer or is_playlist or is_album
        
        vod_name = self._clean(doc("h1").text() or doc(".singer_info h1").text() or doc("title").text())
        vod_pic = self._abs(doc(".djpic img, .pic img, .djpg img, .singer_info img").attr("src"))
        
        vod = {
            "vod_id": url, 
            "vod_name": vod_name, 
            "vod_pic": vod_pic, 
            "vod_play_from": "AAZ音乐网", 
            "vod_content": ""
        }

        if is_list_page:
            eps = self._get_eps(doc)
            
            if len(eps) < 5:
                try:
                    page_urls = set()
                    for a in doc(".page a, .dede_pages a, .pagelist a, .paged a").items():
                        href = a.attr("href")
                        if href and "javascript" not in href and "void" not in href:
                            page_urls.add(self._abs(href))
                    page_urls.discard(url)
                    
                    if page_urls and len(eps) < 50:
                        sorted_urls = sorted(page_urls, key=lambda x: int(re.search(r'[_\/](\d+)\.html', x).group(1)) if re.search(r'[_\/](\d+)\.html', x) else 0)
                        with ThreadPoolExecutor(max_workers=3) as ex:
                            for r in as_completed([ex.submit(lambda u: self._get_eps(self.getpq(u)), u) for u in sorted_urls[:5]]):
                                eps.extend(r.result() or [])
                except:
                    pass
            
            if eps:
                if is_singer:
                    vod["vod_play_from"] = "歌手歌曲"
                elif is_playlist:
                    vod["vod_play_from"] = "歌单歌曲"
                elif is_album:
                    vod["vod_play_from"] = "专辑歌曲"
                else:
                    vod["vod_play_from"] = "播放列表"
                vod["vod_play_url"] = "#".join(eps)
                return {"list": [vod]}

        play_list = []
        mid_match = re.search(r'/(m|song|mp3)/([^/]+)\.html', url)
        if mid_match:
            mid = mid_match.group(2)
            lrc_url = f"{self.host}/plug/down.php?ac=music&lk=lrc&id={mid}"
            play_list = [f"播放${self.e64('0@@@@' + url + '|||' + lrc_url)}"]
        
        elif is_mv:
            vid_match = re.search(r'/(v|video|mp4|mv)/([^/]+)\.html', url)
            if vid_match:
                vid = vid_match.group(2)
                try:
                    mv_urls = self._get_mv_urls(doc, vid)
                    for qn, u in mv_urls:
                        play_list.append(f"{qn}${self.e64('0@@@@'+u)}")
                except:
                    pass

        if not play_list:
            vod["vod_play_url"] = f"解析失败${self.e64('1@@@@'+url)}"
        else:
            vod["vod_play_url"] = "#".join(play_list)
        
        return {"list": [vod]}

    def playerContent(self, flag, id, vipFlags):
        raw = self.d64(id).split("@@@@")[-1]
        url, subt = raw.split("|||") if "|||" in raw else (raw, "")
        url = url.replace(r"\/", "/")

        if ".html" in url and not self.isVideoFormat(url):
            mid_match = re.search(r'/(m|song|mp3)/([^/]+)\.html', url)
            if mid_match:
                mid = mid_match.group(2)
                try:
                    r_url = self._api("/js/play.php", method="POST", data={"id": mid, "type": "music"}, headers={"Referer": self.host + "/", "X-Requested-With": "XMLHttpRequest"})
                    if r_url and self.isVideoFormat(r_url):
                        url = r_url
                    else:
                        try:
                            r_url = self._api("/plug/down.php", {"ac": "music", "id": mid})
                            if r_url and self.isVideoFormat(r_url):
                                url = r_url
                        except:
                            pass
                except:
                    pass
            else:
                vid_match = re.search(r'/(v|video|mp4|mv)/([^/]+)\.html', url)
                if vid_match:
                    vid = vid_match.group(2)
                    try:
                        doc = self.getpq(url)
                        mv_urls = self._get_mv_urls(doc, vid)
                        if mv_urls:
                            url = mv_urls[0][1]
                    except:
                        pass
        
        result = {"parse": 0, "url": url, "header": {"User-Agent": self.headers["User-Agent"]}}
        if "aaz.cx" in url or "5bb3.com" in url or "kuwo.cn" in url:
            result["header"]["Referer"] = self.host + "/"
        
        if subt:
            try:
                r = self.session.get(subt, headers={"Referer": self.host + "/"}, timeout=8)
                lrc_content = r.text
                if lrc_content and len(lrc_content) > 50:
                    lrc_content = self._filter_lrc_ads(lrc_content)
                    result["lrc"] = lrc_content
            except:
                pass
            
        return result

    def _filter_lrc_ads(self, lrc_text):
        lines = lrc_text.splitlines()
        filtered_lines = []
        
        ad_patterns = [
            r'欢迎来访',
            r'本站',
            r'广告',
            r'QQ群',
            r'www\.',
            r'http',
            r'\.com',
            r'\.cn',
            r'\.net',
            r'音乐网',
            r'提供',
            r'下载',
            r'AAZ',
            r'aaz\.cx',
            r'酷我',
            r'酷狗',
        ]
        
        for line in lines:
            if re.match(r'\[\d{2}:\d{2}', line):
                is_ad = False
                for pattern in ad_patterns:
                    if re.search(pattern, line, re.IGNORECASE):
                        is_ad = True
                        break
                if not is_ad:
                    filtered_lines.append(line)
            else:
                if line.strip() and not any(p in line.lower() for p in ['欢迎', '本站', 'aaz', 'www', 'http', '音乐网']):
                    filtered_lines.append(line)
        
        return '\n'.join(filtered_lines)

    def localProxy(self, param):
        url = unquote(param.get("url", ""))
        type_ = param.get("type")
        
        if type_ == "img":
            try:
                return [200, "image/jpeg", self.session.get(url, headers={"Referer": self.host + "/", "User-Agent": self.headers["User-Agent"]}, timeout=8).content, {}]
            except:
                return [404, "text/plain", b"Error", {}]
        
        elif type_ == "lrc":
            try:
                r = self.session.get(url, headers={"Referer": self.host + "/", "User-Agent": self.headers["User-Agent"]}, timeout=8)
                lrc_content = r.text
                lrc_content = self._filter_lrc_ads(lrc_content)
                return [200, "application/octet-stream", lrc_content.encode('utf-8'), {}]
            except:
                return [404, "text/plain", b"Error", {}]
                
        return None

    def _parse_list(self, items, tid=""):
        res = []
        seen = set()
        for li in items.items():
            try:
                all_links = li("a")
                href = ""
                name = ""
                pic = ""
                
                for i in range(all_links.length):
                    a = all_links.eq(i)
                    h = a.attr("href") or ""
                    if h and re.search(r'/(m|s|p|a|v)/', h) and re.search(r'\.(html|php)', h):
                        if not any(x in h for x in ["/user/", "/login/", "javascript:", "void("]):
                            href = h
                            name = a.attr("title") or a.text()
                            break
                
                if not href:
                    continue
                
                abs_href = self._abs(href)
                if abs_href in seen:
                    continue
                seen.add(abs_href)
                
                is_singer = "/s/" in href
                is_playlist = "/p/" in href
                is_album = "/a/" in href
                is_mv = "/v/" in href
                is_song = "/m/" in href
                
                name_el = li(".name")
                if name_el and name_el.text():
                    name = name_el.text()
                
                name = self._clean(name)
                if not name or len(name) < 1:
                    continue
                
                img = li("img")
                if img:
                    pic = self._abs((img.attr("src") or img.attr("data-src") or img.attr("data-original") or ""))
                    if pic:
                        pic = pic.replace('f170_130', 'f500_500').replace('f200_200', 'f500_500').replace('f170_140', 'f500_500').replace('f300_150', 'f500_500')
                        pic = re.sub(r'/\d+x\d+/', '/500x500/', pic)
                
                vod_tag = "folder" if any([is_singer, is_playlist, is_album]) else ""
                
                style_type = "oval" if is_singer else "rect"
                style_ratio = 1 if is_singer else (1.2 if is_mv else 1.33)
                
                res.append({
                    "vod_id": abs_href, 
                    "vod_name": name, 
                    "vod_pic": f"{self.getProxyUrl()}&url={quote(pic)}&type=img" if pic else "", 
                    "vod_tag": vod_tag,
                    "style": {
                        "type": style_type, 
                        "ratio": style_ratio
                    }
                })
            except:
                continue
        return res

    def _get_eps(self, doc):
        eps = []
        seen = set()
        selectors = ".play_list li, .play_list.mt li, .song_list li, .music_list li, .lkmusic_list li"
        
        for li in doc(selectors).items():
            try:
                all_links = li("a")
                href = ""
                for i in range(all_links.length):
                    a = all_links.eq(i)
                    h = a.attr("href") or ""
                    if re.search(r'/(m|song|mp3)/', h):
                        href = h
                        break
                
                if not href:
                    continue
                
                song_match = re.search(r'/(m|song|mp3)/([^/]+)\.html', href)
                if not song_match:
                    continue
                
                full_url = self._abs(href)
                if full_url in seen:
                    continue
                seen.add(full_url)
                
                lrc_part = ""
                mid = song_match.group(2)
                lrc_url = f"{self.host}/plug/down.php?ac=music&lk=lrc&id={mid}"
                lrc_part = f"|||{lrc_url}"
                
                name_el = li(".name")
                song_name = self._clean(name_el.text() if name_el else "" or all_links.eq(0).text() or all_links.eq(0).attr("title"))
                if not song_name:
                    continue
                
                eps.append(f"{song_name}${self.e64('0@@@@' + full_url + lrc_part)}")
            except:
                continue
        
        return eps

    def _get_mv_urls(self, doc, vid):
        urls = []
        html = doc.html() or ""
        
        dplayer_match = re.search(r'quality\s*:\s*(\[.*?\])', html, re.DOTALL)
        if dplayer_match:
            quality_str = dplayer_match.group(1)
            pat1 = r"\{[^}]*name\s*:\s*['\"]([^'\"]+)['\"][^}]*url\s*:\s*['\"]([^'\"]+)['\"]"
            quality_items = re.findall(pat1, quality_str, re.DOTALL)
            if not quality_items:
                pat2 = r"\{[^}]*url\s*:\s*['\"]([^'\"]+)['\"][^}]*name\s*:\s*['\"]([^'\"]+)['\"]"
                quality_items = re.findall(pat2, quality_str, re.DOTALL)
                quality_items = [(n, u) for u, n in quality_items]
            
            for name, url in quality_items:
                full_url = self._abs(url)
                urls.append((name, full_url))
        
        if not urls:
            qualities = [("蓝光", 1080), ("超清", 720), ("高清", 480), ("标清", 420)]
            for name, q in qualities:
                u = f"{self.host}/plug/down.php?ac=vplay&id={vid}&q={q}"
                urls.append((name, u))
        
        return urls

    def _clean(self, text):
        if not text:
            return ""
        patterns = [
            r'AAZ音乐网',
            r'视频下载说明',
            r'视频下载地址',
            r'www\.aaz\.cx',
            r'MP3免费下载',
            r'LRC歌词下载',
            r'全部歌曲',
            r'\[第\d+页\]',
            r'刷新',
            r'每日推荐',
            r'最新',
            r'热门',
            r'推荐',
            r'高清MV',
            r'高清',
            r'无损',
            r'MV',
        ]
        result = text
        for p in patterns:
            result = re.sub(p, '', result, flags=re.I)
        return result.strip()

    def _fetch_filters(self, url):
        try:
            doc = self.getpq(url)
            filters = []
            for i, group in enumerate([doc(s) for s in [".ilingku_fl", ".class_list", ".screen_list", ".box_list", ".nav_list", ".filter"] if doc(s)]):
                opts, seen = [{"n": "全部", "v": "top" if "top" in url else "index"}], set()
                for a in group("a").items():
                    href = a.attr("href") or ""
                    v = href.split("?")[0].rstrip('/').split('/')[-1].replace('.html','')
                    if v and v not in seen:
                        n = a.text().strip()
                        if n and len(n) < 10:
                            opts.append({"n": n, "v": v})
                            seen.add(v)
                if len(opts) > 1:
                    filters.append({"key": f"id{i}" if i else "id", "name": "分类", "value": opts})
            return filters
        except:
            return []

    def _api(self, path, params=None, method="GET", headers=None, data=None):
        try:
            h = self.headers.copy()
            if headers:
                h.update(headers)
            r = (self.session.post if method == "POST" else self.session.get)(
                f"{self.host}{path}", 
                params=params, 
                data=data, 
                headers=h, 
                timeout=10, 
                allow_redirects=False
            )
            
            if loc := r.headers.get("Location"):
                return self._abs(loc.strip())
            
            ct = r.headers.get("Content-Type", "")
            
            if "text/html" in ct and "verifyForm" in r.text:
                if self._verify_human():
                    r = (self.session.post if method == "POST" else self.session.get)(
                        f"{self.host}{path}", 
                        params=params, 
                        data=data, 
                        headers=h, 
                        timeout=10, 
                        allow_redirects=False
                    )
                    if loc := r.headers.get("Location"):
                        return self._abs(loc.strip())
                    ct = r.headers.get("Content-Type", "")
            
            if "application/json" in ct or r.text.strip().startswith("{"):
                try:
                    import json
                    j = json.loads(r.text)
                    result_url = j.get("url", "")
                    if result_url:
                        return self._abs(result_url.replace(r"\/", "/"))
                    if j.get("msg") == 1 and "url" in j:
                        return self._abs(j["url"].replace(r"\/", "/"))
                except:
                    pass
            
            return ""
        except:
            return ""

    def getpq(self, url):
        import time
        abs_url = self._abs(url)
        
        for attempt in range(3):
            try:
                r = self.session.get(abs_url, timeout=15)
                doc = pq(r.text)
                
                has_verify = doc('input[name=csrf_token]').length > 0 and doc('#verifyForm').length > 0
                
                if has_verify and self._verify_attempts < 5:
                    if self._verify_human():
                        self._verified = True
                        continue
                    else:
                        self._verify_attempts += 1
                
                return doc
            except Exception as e:
                time.sleep(0.5)
        
        return pq("<html></html>")

    def _verify_human(self):
        if self._verified:
            return True
        
        try:
            r = self.session.get(self.host, timeout=15)
            doc = pq(r.text)
            
            csrf_token = doc('input[name=csrf_token]').val()
            if not csrf_token:
                self._verified = True
                return True
            
            post_data = {
                'csrf_token': csrf_token, 
                'human_check': 'on'
            }
            post_headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'Referer': self.host + '/',
            }
            
            r2 = self.session.post(
                self.host, 
                data=post_data, 
                headers=post_headers, 
                timeout=15, 
                allow_redirects=True
            )
            
            doc2 = pq(r2.text)
            still_has_verify = doc2('input[name=csrf_token]').length > 0 and doc2('#verifyForm').length > 0
            
            if not still_has_verify:
                self._verified = True
                return True
            
            return False
        except:
            return False

    def _abs(self, url):
        if not url:
            return ""
        if url.startswith("http"):
            return url
        if url.startswith("//"):
            return "http:" + url
        return f"{self.host}{'/' if not url.startswith('/') else ''}{url}"
    
    def e64(self, text):
        return b64encode(text.encode("utf-8")).decode("utf-8")
    
    def d64(self, text):
        return b64decode(text.encode("utf-8")).decode("utf-8")
