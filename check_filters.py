import requests
import json

# Make API request to get facets/filters
url = "https://api.searchspring.net/api/search/search.json"
payload = {
    "siteId": "scfnwy",
    "resultsFormat": "native",
    "resultsPerPage": 1,
    "page": 1
}

headers = {
    'Content-Type': 'application/json'
}
response = requests.post(url, json=payload, headers=headers)
print(f"Status code: {response.status_code}")
print(f"Response: {response.text[:500]}")
data = response.json()

# Print available facets (filters we can use to segment the data)
print("Available filters/facets:")
print(json.dumps(data.get('facets', []), indent=2))

# Also check if there are any other useful fields
print("\n\nOther useful info:")
print(f"Total results: {data.get('pagination', {}).get('totalResults', 0)}")
print(f"Available sorting options: {data.get('sorting', {})}")
