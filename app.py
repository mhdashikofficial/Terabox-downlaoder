import requests
from urllib.parse import urlparse, parse_qs
from flask import Flask, request, render_template

app = Flask(__name__)

def get_terabox_direct_link(share_url):
    # Step 1: Extract share ID from URL
    parsed = urlparse(share_url)
    share_id = parse_qs(parsed.query).get('shareid', [None])[0]
    if not share_id:
        return "Invalid share URL (missing shareid parameter).", None

    # Step 2: Fetch share metadata
    api_url = f"https://www.terabox.com/api/share/getShareInfo?shareid={share_id}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    response = requests.get(api_url, headers=headers)
    if response.status_code != 200:
        return "Failed to fetch share info (network error).", None

    data = response.json()
    if data['errno'] != 0:
        return f"Share error: {data.get('errmsg', 'Unknown error')}", None

    share_data = data['data']
    uk = share_data['uk']
    sign = share_data['sign']
    timestamp = share_data['timestamp']
    file_list = share_data['file_list']

    if not file_list:
        return "No files found in share.", None

    # Assume first file (extend for multiple)
    file_item = file_list[0]
    fid = file_item['fs_id']
    path = file_item.get('path', '')  # For encoded path if needed

    # Step 3: Fetch download info
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
    response = requests.get(download_url, params=params, headers=headers)
    if response.status_code != 200:
        return "Failed to get download info.", None

    dl_data = response.json()
    if dl_data['errno'] != 0:
        return f"Download error: {dl_data.get('errmsg', 'Unknown')}", None

    try:
        # Extract dlink and build full URL
        dlink_info = dl_data['result']['list'][0]
        dlink = dlink_info['dlink']
        time_param = int(timestamp / 1000)  # Convert ms to s
        encoded_path = requests.utils.quote(path) if path else ''
        direct_link = f"{dlink}?fid={fid}&time={time_param}&type=nos&method=download&app_id=250528&path={encoded_path}&ver=4.0&sign={sign}&timestamp={timestamp}&uk={uk}"
        return "Success! Direct link generated.", direct_link
    except (KeyError, IndexError):
        return "Failed to extract download link (may be private/protected).", None

@app.route('/', methods=['GET', 'POST'])
def index():
    error = None
    direct_link = None
    if request.method == 'POST':
        share_url = request.form.get('share_url', '').strip()
        if share_url:
            error, direct_link = get_terabox_direct_link(share_url)
            if error == "Success! Direct link generated.":
                error = None  # Hide success as error
    return render_template('index.html', error=error, direct_link=direct_link)

if __name__ == '__main__':
    app.run(debug=True)
