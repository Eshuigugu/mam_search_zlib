import time
import requests
import json
from bs4 import BeautifulSoup
import os
import pickle
from appdirs import user_data_dir
import re
from urllib.parse import urlencode

# this script does create some files under this directory
appname = "search_zlib"
appauthor = "Eshuigugu"
data_dir = user_data_dir(appname, appauthor)
mam_lang_code_to_str = {'ENG': 'English'}

if not os.path.isdir(data_dir):
    os.makedirs(data_dir)
sess_filepath = os.path.join(data_dir, 'session.pkl')

mam_blacklist_filepath = os.path.join(data_dir, 'blacklisted_ids.txt')
if os.path.exists(mam_blacklist_filepath):
    with open(mam_blacklist_filepath, 'r') as f:
        blacklist = set([int(x.strip()) for x in f.readlines()])
else:
    blacklist = set()

if os.path.exists(sess_filepath):
    sess = pickle.load(open(sess_filepath, 'rb'))
    # only take the cookies
    cookies = sess.cookies
    sess = requests.Session()
    sess.cookies = cookies
else:
    sess = requests.Session()

# find a working mirror
for tries_remaining, API_URL in list(enumerate(['https://zlibrary.shuziyimin.org/search', 'https://zlib.knat.network/search', 'https://zlib.zu1k.com/search']))[::-1]:
    try:
        sess.get(API_URL, params={'query': ''}, timeout=10).json()
    except:
        if tries_remaining == 0:
            raise
        continue
    else:break


# choose an IPFS gateway
ipfs_gateways = ["cloudflare-ipfs.com", "dweb.link", "ipfs.io", "gateway.pinata.cloud"]
ipfs_gateway = ipfs_gateways[2]


def reduce_title(title):
    return re.sub('[-:]( a novel | and other stories | a novella'
    '| a memoir| a thriller| stories| poems| an anthology) *$', '', title, flags=re.IGNORECASE)


def search_zlib(title, authors, language=None):
    queries = [f'"{author}" title:"{title_variant}"' for title_variant in [title, reduce_title(title)]
                    for author in authors[:2]][:10]
    queries = [x for i, x in enumerate(queries) if x not in queries[:i]]
    media_items = []
    for query in queries:
        if language in mam_lang_code_to_str:
            query += f' language:"{mam_lang_code_to_str[language]}"'
        params = {
            'query': query,
            'limit': 5
        }
        time.sleep(1)
        try:
            r = sess.get(API_URL, params=params, timeout=10)
            r_json = r.json()
        except requests.ConnectionError as e:
            print(f'error {e}')
            time.sleep(10)
            continue

        if r.status_code == 200 and r_json['books']:
            for media_item in r_json['books']:
                filename = "%s - %s.%s"%(media_item['title'][:50], media_item['author'][:50].strip(), media_item['extension'])
                media_item['url'] = f'https://{ipfs_gateway}/ipfs/{media_item["ipfs_cid"]}?{urlencode({"filename": filename, "download": "true"})}'
            media_items += r_json['books']
    # ensure each result is unique
    media_items = list({x['url']: x for x in media_items}.values())
    return media_items


def get_mam_requests(limit=5000):
    keepGoing = True
    start_idx = 0
    req_books = []

    # fetch list of requests to search for
    while keepGoing:
        time.sleep(1)
        url = 'https://www.myanonamouse.net/tor/json/loadRequests.php'
        headers = {}
        # fill in mam_id for first run
        headers['cookie'] = 'mam_id='

        query_params = {
            'tor[text]': '',
            'tor[srchIn][title]': 'true',
            'tor[viewType]': 'unful',
            'tor[startDate]': '',
            'tor[endDate]': '',
            'tor[startNumber]': f'{start_idx}',
            'tor[sortType]': 'dateD'
        }
        headers['Content-type'] = 'application/json; charset=utf-8'

        r = sess.get(url, params=query_params, headers=headers, timeout=60)
        if r.status_code >= 300:
            raise Exception(f'error fetching requests. status code {r.status_code} {r.text}')

        req_books += r.json()['data']
        total_items = r.json()['found']
        start_idx += 100
        keepGoing = min(total_items, limit) > start_idx and not \
            {x['id'] for x in req_books}.intersection(blacklist)

    # saving the session lets you reuse the cookies returned by MAM which means you won't have to manually update the mam_id value as often
    with open(sess_filepath, 'wb') as f:
        pickle.dump(sess, f)

    with open(mam_blacklist_filepath, 'a') as f:
        for book in req_books:
            f.write(str(book['id']) + '\n')
            book['url'] = 'https://www.myanonamouse.net/tor/viewRequest.php/' + \
                          str(book['id'])[:-5] + '.' + str(book['id'])[-5:]
            book['title'] = BeautifulSoup(book["title"], features="lxml").text
            if book['authors']:
                book['authors'] = [author for k, author in json.loads(book['authors']).items()]
    return req_books


def main():
    req_books = get_mam_requests()
    req_books_reduced = [x for x in req_books if
                         (x['cat_name'].startswith('Ebooks '))
                         and x['filled'] == 0
                         and x['torsatch'] == 0
                         and x['id'] not in blacklist]

    for book in req_books_reduced:
        title = book['title'].replace('"', '')
        authors = [x.replace('"', '') for x in book['authors']]
        hits = search_zlib(title, authors, language=book['lang_code'])
        if hits:
            print(book['title'])
            print(' ' * 2 + book['url'])
            if len(hits) > 5:
                print(' ' * 2 + f'got {len(hits)} hits')
                print(' ' * 2 + f'showing first 5 results')
                hits = hits[:5]
            for hit in hits:
                print(' ' * 2 + hit["title"])
                print(' ' * 4 + hit['url'])
            print()


if __name__ == '__main__':
    main()

