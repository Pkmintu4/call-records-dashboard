import psycopg2
from langdetect import detect

def detect_language(text):
    try:
        lang = detect(text)
        if lang == 'te':
            return 'Telugu'
        elif lang == 'en':
            return 'English'
        else:
            return 'Mixed'
    except:
        return 'Mixed'

conn = psycopg2.connect(
    dbname="transcripts", user="myuser", password="mypass", host="127.0.0.1"
)
cur = conn.cursor()
cur.execute("SELECT id, text FROM transcripts WHERE language IS NULL;")
for id, text in cur.fetchall():
    lang = detect_language(text)
    cur.execute("UPDATE transcripts SET language=%s WHERE id=%s", (lang, id))
conn.commit()
cur.close()
conn.close()
