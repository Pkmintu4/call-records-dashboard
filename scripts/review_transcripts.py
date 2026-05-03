import psycopg2
import requests

# MCP Toolbox API endpoint (adjust if running locally or on a different port)
MCP_API_URL = "http://localhost:8080/tools/transcript_quality_review"

DB_CONFIG = {
    "dbname": "transcripts",
    "user": "myuser",
    "password": "mypass",
    "host": "127.0.0.1"
}

def fetch_unreviewed_transcripts():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute("SELECT id, text FROM transcripts WHERE reviewed = FALSE AND (language = 'Mixed' OR language = 'Telugu')")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def review_transcript(text):
    payload = {"text": text}
    response = requests.post(MCP_API_URL, json=payload)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error from MCP Toolbox: {response.status_code}")
        return None

def update_transcript_review(id, suggestions, score):
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute(
        "UPDATE transcripts SET reviewed = TRUE, confidence = %s WHERE id = %s",
        (score, id)
    )
    conn.commit()
    cur.close()
    conn.close()
    print(f"Transcript {id} reviewed. Score: {score}")

def main():
    transcripts = fetch_unreviewed_transcripts()
    for id, text in transcripts:
        review = review_transcript(text)
        if review:
            suggestions = review.get("suggestions", "")
            score = review.get("quality_score", 0.0)
            update_transcript_review(id, suggestions, score)

if __name__ == "__main__":
    main()
