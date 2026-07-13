# -*- coding: utf-8 -*-
"""
AAZ音乐网 - www.aaz.cx
"""
import re
import json
import sys
import time
from urllib.parse import quote, urljoin
from base.spider import Spider


class Spider(Spider):
    def __init__(self):
        super(Spider, self).__init__()
        self.host = "http://www.aaz.cx"
        self.name = "AAZ音乐网"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
            'Referer': self.host
        }
        self._verify_done = False
        self._session = None

    def getName(self):
        return "AAZ音乐网"

    def init(self, extend=""):
        pass

    def _get_session(self):
        import requests
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update(self.headers)
            self._session.verify = False
        return self._session

    def _ensure_verify(self):
        if self._verify_done:
            return
        session = self._get_session()
        try:
            r = session.get(self.host, timeout=15)
            r.encoding = 'utf-8'
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(r.text, 'html.parser')
            csrf_input = soup.find('input', {'name': 'csrf_token'})
            if csrf_input:
                csrf_token = csrf_input.get('value', '')
                data = {'csrf_token': csrf_token, 'human_check': 'on'}
                r2 = session.post(self.host, data=data, timeout=15)
                r2.encoding = 'utf-8'
            self._verify_done = True
        except Exception as e:
            print(f'[{self.name}] 验证失败: {e}')

    def _fetch_page(self, url, retries=2):
        self._ensure_verify()
        session = self._get_session()
        for attempt in range(retries + 1):
            try:
                resp = session.get(url, timeout=15)
                resp.encoding = 'utf-8'
                if 'csrf_token' in resp.text and '我不是人机' in resp.text:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    csrf_input = soup.find('input', {'name': 'csrf_token'})
                    if csrf_input:
                        csrf_token = csrf_input.get('value', '')
                        data = {'csrf_token': csrf_token, 'human_check': 'on'}
                        resp = session.post(url, data=data, timeout=15)
                        resp.encoding = 'utf-8'
                if resp.status_code == 200:
                    return resp.text
                if attempt < retries:
                    time.sleep(1)
                    continue
            except Exception as e:
                if attempt < retries:
                    time.sleep(1)
                    continue
                print(f'[{self.name}] 请求失败: {url}, 错误: {e}')
                return ''
        return ''

    def _fetch_api(self, url, data=None, retries=2):
        self._ensure_verify()
        session = self._get_session()
        for attempt in range(retries + 1):
            try:
                if data:
                    resp = session.post(url, data=data, timeout=15)
                else:
                    resp = session.get(url, timeout=15)
                resp.encoding = 'utf-8'
                if resp.status_code == 200:
                    return resp.text
                if attempt < retries:
                    time.sleep(1)
                    continue
            except Exception as e:
                if attempt < retries:
                    time.sleep(1)
                    continue
                print(f'[{self.name}] API请求失败: {url}, 错误: {e}')
                return ''
        return ''

    def homeContent(self, filter):
        classes = [
            {"type_id": "new", "type_name": "新歌榜"},
            {"type_id": "top", "type_name": "TOP榜单"},
            {"type_id": "singer", "type_name": "歌手"},
            {"type_id": "playlist", "type_name": "歌单"},
            {"type_id": "album", "type_name": "专辑"},
        ]
        filters = {
            "new": [{"key": "quality", "name": "音质", "value": [{"n": "标准128K", "v": "标准128K"}, {"n": "高清192K", "v": "高清192K"}, {"n": "超清320K", "v": "超清320K"}, {"n": "无损APE", "v": "无损APE"}]}],
            "top": [{"key": "quality", "name": "音质", "value": [{"n": "标准128K", "v": "标准128K"}, {"n": "高清192K", "v": "高清192K"}, {"n": "超清320K", "v": "超清320K"}, {"n": "无损APE", "v": "无损APE"}]}],
            "singer": [{"key": "quality", "name": "音质", "value": [{"n": "标准128K", "v": "标准128K"}, {"n": "高清192K", "v": "高清192K"}, {"n": "超清320K", "v": "超清320K"}, {"n": "无损APE", "v": "无损APE"}]}],
            "playlist": [{"key": "quality", "name": "音质", "value": [{"n": "标准128K", "v": "标准128K"}, {"n": "高清192K", "v": "高清192K"}, {"n": "超清320K", "v": "超清320K"}, {"n": "无损APE", "v": "无损APE"}]}],
            "album": [{"key": "quality", "name": "音质", "value": [{"n": "标准128K", "v": "标准128K"}, {"n": "高清192K", "v": "高清192K"}, {"n": "超清320K", "v": "超清320K"}, {"n": "无损APE", "v": "无损APE"}]}],
        }
        return {'class': classes, 'filters': filters, 'list': []}

    def homeVideoContent(self):
        try:
            videos = self._fetch_home()
            return {'list': videos}
        except Exception as e:
            print(f'[{self.name}] 首页爬取失败: {e}')
            return {'list': []}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = int(pg) if pg and str(pg).isdigit() else 1
            if tid == 'new':
                videos = self._fetch_list('list/new.html', page)
            elif tid == 'top':
                videos = self._fetch_list('list/top.html', page)
            elif tid == 'singer':
                videos = self._fetch_singer_list(page)
            elif tid == 'playlist':
                videos = self._fetch_playlist_list(page)
            elif tid == 'album':
                videos = self._fetch_album_list(page)
            else:
                videos = []
            return {
                'page': page,
                'pagecount': 9999,
                'limit': 30,
                'total': 99999,
                'list': videos
            }
        except Exception as e:
            print(f'[{self.name}] 分类爬取失败: {e}')
            return {'page': int(pg) if pg else 1, 'pagecount': 0, 'limit': 30, 'total': 0, 'list': []}

    def detailContent(self, ids):
        try:
            vod_id = ids[0] if isinstance(ids, list) else ids
            if vod_id.startswith('singer_'):
                detail = self._fetch_singer_detail(vod_id.replace('singer_', ''))
            elif vod_id.startswith('playlist_'):
                detail = self._fetch_playlist_detail(vod_id.replace('playlist_', ''))
            elif vod_id.startswith('album_'):
                detail = self._fetch_album_detail(vod_id.replace('album_', ''))
            elif vod_id.startswith('song_'):
                detail = self._fetch_song_detail(vod_id.replace('song_', ''))
            else:
                detail = self._fetch_song_detail(vod_id)
            if detail:
                return {'list': [detail]}
            return {'list': []}
        except Exception as e:
            print(f'[{self.name}] 详情爬取失败: {e}')
            return {'list': []}

    def playerContent(self, flag, id, vipFlags):
        try:
            play_url = ''
            pic = ''
            lrc = ''
            quality_flag = ''

            if id and id.startswith('http'):
                play_url = id
            elif '$' in str(id):
                parts = str(id).split('$', 1)
                if len(parts) == 2:
                    play_url = parts[1]
            else:
                play_url = id

            if play_url and not play_url.startswith('http'):
                api_url = f"{self.host}/js/play.php"
                result = self._fetch_api(api_url, data={'id': play_url, 'type': 'music'})
                if result:
                    try:
                        data = json.loads(result)
                        if data.get('url'):
                            play_url = data['url']
                            pic = data.get('pic', '')
                            lrc_url = data.get('lrc', '')
                            if lrc_url:
                                lrc_content = self._fetch_api(lrc_url)
                                if lrc_content:
                                    try:
                                        lrc_data = json.loads(lrc_content)
                                        lrc = lrc_data.get('lrc', '')
                                    except:
                                        lrc = lrc_content

                            kuwo_rid = self._extract_kuwo_rid(pic)
                            if kuwo_rid:
                                quality_url = self._get_quality_url(kuwo_rid, flag)
                                if quality_url:
                                    play_url = quality_url
                    except:
                        pass

            header = '{"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}'
            return {
                'parse': 0,
                'playUrl': '',
                'url': play_url,
                'header': header,
                'pic': pic,
                'lrc': lrc,
            }
        except Exception as e:
            print(f'[{self.name}] 播放失败: {e}')
            return {
                'parse': 1,
                'playUrl': '',
                'url': str(id),
            }

    def _extract_kuwo_rid(self, pic_url):
        if not pic_url:
            return None
        match = re.search(r'/(\d+)\.\w+$', pic_url)
        if match:
            return match.group(1)
        return None

    def _get_quality_url(self, kuwo_rid, quality_flag):
        quality_map = {
            '标准128K': (128, 'mp3'),
            '高清192K': (192, 'mp3'),
            '超清320K': (320, 'mp3'),
            '无损APE': (2000, 'ape'),
        }
        if quality_flag not in quality_map:
            quality_flag = '超清320K'
        bitrate, fmt = quality_map[quality_flag]
        try:
            kuwo_url = (
                f'https://nmobi.kuwo.cn/mobi.s?f=web&user=0'
                f'&source=kwplayer_ar_4.4.2.7_B_nuoweida_vh.apk'
                f'&type=convert_url_with_sign&rid={kuwo_rid}'
                f'&bitrate={bitrate}&format={fmt}'
            )
            kuwo_headers = {
                'User-Agent': 'Mozilla/5.0 (Linux; Android 10)',
                'Referer': 'https://www.kuwo.cn/'
            }
            import requests as req
            r = req.get(kuwo_url, headers=kuwo_headers, timeout=10, verify=False)
            data = r.json()
            if data.get('code') == 200 and data.get('data') and data['data'].get('url'):
                return data['data']['url']
        except Exception as e:
            print(f'[{self.name}] 获取音质失败: {e}')
        return None

    def getQualityList(self):
        return ['标准128K', '高清192K', '超清320K', '无损APE']

    def searchContent(self, key, quick, pg="1"):
        try:
            page = int(pg) if pg and str(pg).isdigit() else 1
            videos = self._fetch_search(key, page)
            return {'list': videos}
        except Exception as e:
            print(f'[{self.name}] 搜索失败: {e}')
            return {'list': []}

    def _parse_song_from_item(self, item):
        name_div = item.find('div', class_='name')
        pic_div = item.find('div', class_='pic')
        if not name_div:
            return None
        a = name_div.find('a')
        if not a:
            return None
        href = a.get('href', '')
        name = a.text.strip().replace('mv', '').strip()
        if not href or not name:
            return None
        song_id = href.replace('/m/', '').replace('.html', '')
        duration = pic_div.text.strip() if pic_div else ''
        return {
            'vod_id': f'song_{song_id}',
            'vod_name': name,
            'vod_pic': '',
            'vod_remarks': duration,
        }

    def _fetch_home(self):
        html = self._fetch_page(self.host)
        if not html:
            return []
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        videos = []
        seen = set()
        items = soup.find_all('div', class_='item')
        for item in items:
            vod = self._parse_song_from_item(item)
            if vod and vod['vod_id'] not in seen:
                seen.add(vod['vod_id'])
                videos.append(vod)
        if not videos:
            name_divs = soup.find_all('div', class_='name')
            for nd in name_divs:
                a = nd.find('a')
                if a:
                    href = a.get('href', '')
                    name = a.text.strip().replace('mv', '').strip()
                    if '/m/' in href and name and len(name) > 1 and href not in seen:
                        seen.add(href)
                        song_id = href.replace('/m/', '').replace('.html', '')
                        videos.append({
                            'vod_id': f'song_{song_id}',
                            'vod_name': name,
                            'vod_pic': '',
                            'vod_remarks': '歌曲',
                        })
        return videos[:50]

    def _fetch_list(self, path, page=1):
        if page <= 1:
            url = f"{self.host}/{path}"
        else:
            url = f"{self.host}/{path.replace('.html', f'/{page}.html')}"
        html = self._fetch_page(url)
        if not html:
            return []
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        videos = []
        seen = set()
        name_divs = soup.find_all('div', class_='name')
        for nd in name_divs:
            a = nd.find('a')
            if a:
                href = a.get('href', '')
                name = a.text.strip().replace('mv', '').strip()
                if '/m/' in href and name and len(name) > 1 and href not in seen:
                    seen.add(href)
                    song_id = href.replace('/m/', '').replace('.html', '')
                    videos.append({
                        'vod_id': f'song_{song_id}',
                        'vod_name': name,
                        'vod_pic': '',
                        'vod_remarks': '歌曲',
                    })
        return videos

    def _fetch_singer_list(self, page=1):
        url = f"{self.host}/singerlist/index/index/index/index.html"
        if page > 1:
            url = f"{self.host}/singerlist/index/index/index/index-{page}.html"
        html = self._fetch_page(url)
        if not html:
            return []
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        videos = []
        singer_list = soup.find('div', class_='singer_list')
        if singer_list:
            items = singer_list.find_all('a')
            seen = set()
            for item in items:
                href = item.get('href', '')
                title = item.get('title', '') or item.text.strip()
                img = item.find('img')
                img_src = ''
                if img:
                    img_src = img.get('src', '') or img.get('data-original', '')
                if title and href and href not in seen:
                    seen.add(href)
                    singer_id = href.replace('/s/', '').replace('.html', '')
                    videos.append({
                        'vod_id': f'singer_{singer_id}',
                        'vod_name': title,
                        'vod_pic': img_src,
                        'vod_remarks': '歌手',
                    })
        return videos

    def _fetch_playlist_list(self, page=1):
        url = f"{self.host}/playtype/index.html"
        if page > 1:
            url = f"{self.host}/playtype/index/{page}.html"
        html = self._fetch_page(url)
        if not html:
            return []
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        videos = []
        links = soup.find_all('a')
        seen = set()
        for l in links:
            href = l.get('href', '')
            text = l.text.strip()
            if '/p/' in href and text and len(text) > 4 and href not in seen:
                seen.add(href)
                pl_id = href.replace('/p/', '').replace('.html', '')
                videos.append({
                    'vod_id': f'playlist_{pl_id}',
                    'vod_name': text,
                    'vod_pic': '',
                    'vod_remarks': '歌单',
                })
        return videos

    def _fetch_album_list(self, page=1):
        url = f"{self.host}/albumlist/index.html"
        if page > 1:
            url = f"{self.host}/albumlist/index/{page}.html"
        html = self._fetch_page(url)
        if not html:
            return []
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        videos = []
        links = soup.find_all('a')
        seen = set()
        for l in links:
            href = l.get('href', '')
            text = l.text.strip()
            if '/a/' in href and text and len(text) > 2 and href not in seen:
                seen.add(href)
                album_id = href.replace('/a/', '').replace('.html', '')
                videos.append({
                    'vod_id': f'album_{album_id}',
                    'vod_name': text,
                    'vod_pic': '',
                    'vod_remarks': '专辑',
                })
        return videos

    def _build_quality_detail(self, vod_id, vod_name, vod_pic, vod_content, songs, play_from_name):
        prefix = '微信公众号"源力软件汇" '
        qualities = ['标准128K', '高清192K', '超清320K', '无损APE']
        song_list = '#'.join(songs)
        vod_play_from = '$$$'.join(qualities)
        vod_play_url = '$$$'.join([song_list for _ in qualities])
        return {
            'vod_id': vod_id,
            'vod_name': vod_name,
            'vod_pic': vod_pic,
            'vod_content': f'{prefix}{vod_content}',
            'vod_play_from': vod_play_from,
            'vod_play_url': vod_play_url,
        }

    def _fetch_singer_detail(self, singer_id):
        url = f"{self.host}/s/{singer_id}.html"
        html = self._fetch_page(url)
        if not html:
            return None
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        title_tag = soup.title
        singer_name = ''
        if title_tag:
            title_text = title_tag.string or ''
            singer_name = title_text.split('全部歌曲')[0].strip() if '全部歌曲' in title_text else title_text.split('_')[0].strip()

        songs = []
        seen = set()
        name_divs = soup.find_all('div', class_='name')
        for nd in name_divs:
            a = nd.find('a')
            if a:
                href = a.get('href', '')
                name = a.text.strip().replace('mv', '').strip()
                if '/m/' in href and name and len(name) > 1 and href not in seen:
                    seen.add(href)
                    song_id = href.replace('/m/', '').replace('.html', '')
                    songs.append(f'{name}${song_id}')

        if not songs:
            return None

        return self._build_quality_detail(
            f'singer_{singer_id}',
            singer_name or '未知歌手',
            '',
            f'歌手: {singer_name}，共{len(songs)}首歌曲',
            songs,
            f'{singer_name}的歌曲'
        )

    def _fetch_playlist_detail(self, pl_id):
        url = f"{self.host}/p/{pl_id}.html"
        html = self._fetch_page(url)
        if not html:
            return None
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        title_tag = soup.title
        pl_name = ''
        if title_tag:
            title_text = title_tag.string or ''
            pl_name = title_text.split('歌单')[0].strip() if '歌单' in title_text else title_text.split('_')[0].strip()

        songs = []
        seen = set()
        name_divs = soup.find_all('div', class_='name')
        for nd in name_divs:
            a = nd.find('a')
            if a:
                href = a.get('href', '')
                name = a.text.strip().replace('mv', '').strip()
                if '/m/' in href and name and len(name) > 1 and href not in seen:
                    seen.add(href)
                    song_id = href.replace('/m/', '').replace('.html', '')
                    songs.append(f'{name}${song_id}')

        if not songs:
            return None

        return self._build_quality_detail(
            f'playlist_{pl_id}',
            pl_name or '未知歌单',
            '',
            f'歌单: {pl_name}，共{len(songs)}首歌曲',
            songs,
            pl_name
        )

    def _fetch_album_detail(self, album_id):
        url = f"{self.host}/a/{album_id}.html"
        html = self._fetch_page(url)
        if not html:
            return None
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        title_tag = soup.title
        album_name = ''
        if title_tag:
            title_text = title_tag.string or ''
            album_name = title_text.split('的专辑')[0].strip() if '的专辑' in title_text else title_text.split('_')[0].strip()

        songs = []
        seen = set()
        name_divs = soup.find_all('div', class_='name')
        for nd in name_divs:
            a = nd.find('a')
            if a:
                href = a.get('href', '')
                name = a.text.strip().replace('mv', '').strip()
                if '/m/' in href and name and len(name) > 1 and href not in seen:
                    seen.add(href)
                    song_id = href.replace('/m/', '').replace('.html', '')
                    songs.append(f'{name}${song_id}')

        if not songs:
            return None

        return self._build_quality_detail(
            f'album_{album_id}',
            album_name or '未知专辑',
            '',
            f'专辑: {album_name}，共{len(songs)}首歌曲',
            songs,
            f'{album_name}专辑'
        )

    def _fetch_song_detail(self, song_id):
        url = f"{self.host}/m/{song_id}.html"
        html = self._fetch_page(url)
        if not html:
            return None
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        title_tag = soup.title
        song_name = ''
        if title_tag:
            title_text = title_tag.string or ''
            song_name = title_text.split('Mp3')[0].strip() if 'Mp3' in title_text else title_text.split('mp3')[0].strip() if 'mp3' in title_text else title_text.split('_')[0].strip()

        pic = ''
        img = soup.find('img', id='mcover')
        if img:
            pic = img.get('src', '')

        if not pic:
            img = soup.find('img', class_='djpic')
            if img:
                pic = img.get('src', '')

        if not pic:
            img = soup.find('div', class_='play_left')
            if img:
                img2 = img.find('img')
                if img2:
                    pic = img2.get('src', '')

        prefix = '微信公众号"源力软件汇" '
        qualities = ['标准128K', '高清192K', '超清320K', '无损APE']
        song_item = f'{song_name}${song_id}'
        vod_play_from = '$$$'.join(qualities)
        vod_play_url = '$$$'.join([song_item for _ in qualities])

        return {
            'vod_id': f'song_{song_id}',
            'vod_name': song_name or '未知歌曲',
            'vod_pic': pic,
            'vod_content': f'{prefix}歌曲: {song_name}',
            'vod_play_from': vod_play_from,
            'vod_play_url': vod_play_url,
        }

    def _fetch_search(self, keyword, page=1):
        url = f"{self.host}/so.php?wd={quote(keyword)}"
        html = self._fetch_page(url)
        if not html:
            return []
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        videos = []
        seen = set()
        name_divs = soup.find_all('div', class_='name')
        for nd in name_divs:
            a = nd.find('a')
            if a:
                href = a.get('href', '')
                name = a.text.strip().replace('mv', '').strip()
                if '/m/' in href and name and len(name) > 1 and href not in seen:
                    seen.add(href)
                    song_id = href.replace('/m/', '').replace('.html', '')
                    videos.append({
                        'vod_id': f'song_{song_id}',
                        'vod_name': name,
                        'vod_pic': '',
                        'vod_remarks': '歌曲',
                    })
        if not videos:
            links = soup.find_all('a')
            for l in links:
                href = l.get('href', '')
                text = l.text.strip()
                if '/m/' in href and text and len(text) > 2 and href not in seen:
                    seen.add(href)
                    song_id = href.replace('/m/', '').replace('.html', '')
                    name = text.replace('mv', '').strip()
                    if not name:
                        continue
                    videos.append({
                        'vod_id': f'song_{song_id}',
                        'vod_name': name,
                        'vod_pic': '',
                        'vod_remarks': '歌曲',
                    })
        return videos
