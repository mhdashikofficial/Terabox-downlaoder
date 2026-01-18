import requests
import re
from urllib.parse import urlparse, parse_qs
from flask import Flask, request, render_template

app = Flask(__name__)

def get_terabox_direct_link(share_url):
    # Normalize domain to official Terabox (handles mirrors like 1024terabox.com)
    parsed = urlparse(share_url)
    if parsed.netloc != 'www.terabox.com':
        normalized_url = share_url.replace(parsed.netloc, 'www.terabox.com', 1)
    else:
        normalized_url = share_url

    # Extract shareid if present in query
    query_shareid = parse_qs(parsed.query).get('shareid', [None])[0]
    if query_shareid:
        return _get_direct_link_with_shareid(query_shareid)

    # For short links: Extract shorturl from path (e.g., /s/1ABC... -> 1ABC...)
    path_parts = parsed.path.split('/s/')
    if len(path_parts) != 2 or not path_parts[1]:
        return "Invalid short link format (expected /s/<shortcode>).", None

    shorturl = path_parts[1].split('?')[0]  # Remove any query if present
    return _get_direct_link_with_shorturl(normalized_url, shorturl)

def _get_direct_link_with_shareid(shareid):
    api_url = f"https://www.terabox.com/api/share/getShareInfo?shareid={shareid}"
    headers = _get_headers()
    response = requests.get(api_url, headers=headers)
    if response.status_code != 200:
        return "Failed to fetch share info (network error).", None

    data = response.json()
    if data['errno'] != 0:
        return f"Share error: {data.get('errmsg', 'Unknown error')}", None

    return _build_direct_link_from_data(data['data'])

def _get_direct_link_with_shorturl(share_url, shorturl):
    # Fetch page to extract logid and jsToken
    headers = _get_headers()
    try:
        response = requests.get(share_url, headers=headers, allow_redirects=True)
        if response.status_code != 200:
            return "Failed to load share page (may be invalid or private).", None
    except requests.RequestException:
        return "Network error fetching share page.", None

    # Extract logid and jsToken from HTML (common in <script> tags)
    logid_match = re.search(r'"logid"\s*:\s*"([^"]+)"', response.text)
    jstoken_match = re.search(r'"jsToken"\s*:\s*"([^"]+)"', response.text)
    if not logid_match or not jstoken_match:
        return "Failed to extract required tokens (share may require login).", None

    logid = logid_match.group(1)
    js_token = jstoken_match.group(1)

    # Call /share/list API with shorturl
    api_url = (
        f"https://www.terabox.com/share/list?"
        f"app_id=250528&channel=0&clienttype=0&logid={logid}&jsToken={js_token}&"
        f"num=20&order=asc&root=1&shorturl={shorturl}&web=1"
    )
    response = requests.get(api_url, headers=headers)
    if response.status_code != 200:
        return "Failed to fetch share list.", None

    data = response.json()
    if data['errno'] != 0:
        return f"Share list error: {data.get('errmsg', 'Unknown')}", None

    share_data = data['data']
    if not share_data.get('file_list'):
        return "No files found in share.", None

    # Flatten file_list (handles folders minimally; take first file)
    file_list = []
    def flatten_files(items):
        for item in items:
            if item['isdir']:
                flatten_files(item['list'])
            else:
                file_list.append(item)
    flatten_files(share_data['file_list'])
    if not file_list:
        return "No downloadable files found.", None

    # Get share params from share_info (or fallback)
    share_info_url = f"https://www.terabox.com/api/share/getShareInfo?shorturl={shorturl}"
    si_response = requests.get(share_info_url, headers=headers)
    si_data = si_response.json()
    if si_data['errno'] == 0:
        share_params = si_data['data']
    else:
        return "Failed to get share params.", None

    uk = share_params['uk']
    sign = share_params['sign']
    timestamp = share_params['timestamp']

    # Assume first file
    file_item = file_list[0]
    fid = file_item['fs_id']
    path = file_item.get('path', '')

    # Fetch download info
    return _get_download_dlink(uk, fid, sign, timestamp, path)

def _get_download_dlink(uk, fid, sign, timestamp, path):
    download_url = "https://www.terabox.com/rest/2.0/pcs/file"
    params = {
        'method': 'batch',
        'app_id': '250528',
        'ver': '4.0',
        'format': 'json',
        'channel': 'chunlei',
        'clienttype': '0',
        'web': '1',
        'type': 'tmp',
        'action': 'download',
        'uk': uk,
        'primaryid': '0',
        'fid_list': f'[{fid}]',
        'sign': sign,
        'timestamp': timestamp,
    }
    headers = _get_headers()
    response = requests.get(download_url, params=params, headers=headers)
    if response.status_code != 200:
        return "Failed to get download info.", None

    dl_data = response.json()
    if dl_data['errno'] != 0:
        return f"Download error: {dl_data.get('errmsg', 'Unknown')}", None

    try:
        dlink_info = dl_data['result']['list'][0]
        dlink = dlink_info['dlink']
        time_param = int(timestamp / 1000)
        encoded_path = requests.utils.quote(path) if path else ''
        direct_link = (
            f"{dlink}?"
            f"fid={fid}&time={time_param}&type=nos&method=download&app_id=250528"
            f"&path={encoded_path}&ver=4.0&sign={sign}&timestamp={timestamp}&uk={uk}"
        )
        return "Success! Direct link generated.", direct_link
    except (KeyError, IndexError):
        return "Failed to extract download link (may be private/protected).", None

def _build_direct_link_from_data(share_data):
    uk = share_data['uk']
    sign = share_data['sign']
    timestamp = share_data['timestamp']
    file_list = share_data['file_list']

    if not file_list:
        return "No files found in share.", None

    file_item = file_list[0]
    fid = file_item['fs_id']
    path = file_item.get('path', '')

    return _get_download_dlink(uk, fid, sign, timestamp, path)

def _get_headers():
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Referer': 'https://www.terabox.com/',
    }

@app.route('/', methods=['GET', 'POST'])
def index():
    error = None
    direct_link = None
    if request.method == 'POST':
        share_url = request.form.get('share_url', '').strip()
        if share_url:
            error_msg, direct_link = get_terabox_direct_link(share_url)
            if error_msg == "Success! Direct link generated.":
                error = None
            else:
                error = error_msg
    return render_template('index.html', error=error, direct_link=direct_link)

if __name__ == '__main__':
    app.run(debug=True)
