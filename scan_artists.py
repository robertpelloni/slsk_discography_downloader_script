import requests

artists = "1200 Micrograms, 1200 Mics, 1300 Micrograms, Bansi, Chicago, Raja Ram, Riktam, Riktam & Bansi, Growling Mad Scientists, GMS, Growling Machines, Growling Machine Sex, G.M.S., Ajja, Outsiders, Psysex, Talamasca, Space Tribe, ESP, E.S.P., Mad Maxx, Mad Tribe, DJ Stryker, Dickster, Laughing Buddha, Space Buddha, Alienatic, Electric Universe, Volcano, Alien Project, Save The Robot, Hypnocoustics, Faders, Soundaholix, 3 Of Life, Avalon, Astrix, DJ Technorch, Technorch, Betwixt & Between, Beatmania IIDX OST, Beatmania IIDX Soundtrack, Ace Ventura, KoxBox"
artist_list = [a.strip() for a in artists.split(',')]

url = "http://localhost:8000/api/scan"
payload = {
    "artist_names": artist_list,
    "depth": 1
}

try:
    print(f"Starting scan for {len(artist_list)} artists...")
    response = requests.post(url, json=payload, timeout=600)
    if response.status_code == 200:
        print("Scan complete. Artists added to Managed List.")
    else:
        print(f"Error: {response.status_code} - {response.text}")
except Exception as e:
    print(f"Failed to connect to API: {e}")
