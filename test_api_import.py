
import requests
import json

def test_import_api():
    url = "http://localhost:5000/api/cards/import"
    payload = {
        "name": "Black Lotus", # Prova con un'altra carta
        "tcg": "mtg"
    }
    
    print(f"Sending POST to {url} with payload: {payload}")
    
    try:
        response = requests.post(url, json=payload)
        print(f"Status Code: {response.status_code}")
        try:
            print("Response JSON:", response.json())
        except:
            print("Response Text:", response.text)
            
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    test_import_api()
