import requests
import json

api_url = "https://zyfff9.a.searchspring.io/api/search/search.json"

params = {
    'siteId': 'zyfff9',
    'page': 1,
    'bgfilter.categories_hierarchy': 'Worldwide',
    'bgfilter.ss_ad': '0',
    'redirectResponse': 'full',
    'resultsFormat': 'native'
}

headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    'Accept': '*/*',
    'Referer': 'https://www.mysticstamp.com/'
}

print("Fetching API data...")
response = requests.get(api_url, params=params, headers=headers, timeout=30)
response.raise_for_status()

data = response.json()

print(f"\nAPI Response Keys: {list(data.keys())}")

results = data.get('results', [])
print(f"\nTotal results: {len(results)}")

if results:
    print("\n=== FIRST RESULT ===")
    first = results[0]
    print(f"Keys in first result: {list(first.keys())}")
    print(f"\nFirst result data:")
    print(json.dumps(first, indent=2))

    print("\n=== SECOND RESULT ===")
    if len(results) > 1:
        second = results[1]
        print(json.dumps(second, indent=2))
