import requests
import sys
sys.path.insert(0, '.')
from config import GROQ_API_KEY

url = "https://api.groq.com/openai/v1/models"
headers = {
    "Authorization": f"Bearer {GROQ_API_KEY}",
    "Content-Type": "application/json"
}

response = requests.get(url, headers=headers)
models = response.json()

print("\nДоступные модели Groq:")
for m in sorted(models.get('data', []), key=lambda x: x['id']):
    print(f"  {m['id']}")