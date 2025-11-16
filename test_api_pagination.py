import requests
import json

api_url = "https://zyfff9.a.searchspring.io/api/search/search.json"

# Test different parameters to get more results
test_params = [
    {'siteId': 'zyfff9', 'page': 1, 'bgfilter.categories_hierarchy': 'Worldwide', 'resultsFormat': 'native'},
    {'siteId': 'zyfff9', 'page': 1, 'bgfilter.categories_hierarchy': 'Worldwide', 'resultsFormat': 'native', 'resultsPerPage': 96},
    {'siteId': 'zyfff9', 'page': 1, 'bgfilter.categories_hierarchy': 'Worldwide', 'resultsFormat': 'native', 'per_page': 96},
    {'siteId': 'zyfff9', 'page': 1, 'bgfilter.categories_hierarchy': 'Worldwide', 'resultsFormat': 'native', 'limit': 96},
]

headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    'Accept': '*/*',
    'Referer': 'https://www.mysticstamp.com/'
}

for i, params in enumerate(test_params):
    print(f"\n{'='*60}")
    print(f"Test {i+1}: {params}")
    print('='*60)

    try:
        response = requests.get(api_url, params=params, headers=headers, timeout=30)
        response.raise_for_status()

        data = response.json()

        results = data.get('results', [])
        pagination = data.get('pagination', {})

        print(f"Results returned: {len(results)}")
        print(f"Pagination info: {json.dumps(pagination, indent=2)}")

    except Exception as e:
        print(f"Error: {e}")
