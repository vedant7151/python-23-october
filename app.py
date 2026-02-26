from flask import Flask, request, render_template_string, jsonify
import psycopg2
from psycopg2 import sql
import os
from dotenv import load_dotenv
# import openai
from google import genai
from flask import Flask, request, jsonify
# import tempfile

# ---------- Load Environment Variables ----------
load_dotenv()
app = Flask(__name__)
# openai.api_key = os.getenv("OPENAI_API_KEY")


client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))



# ---------- Database Connection ----------
def get_connection():
    return psycopg2.connect(os.getenv("DATABASE_URL"), sslmode="require")

# ---------- HTML Frontend ----------
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Video Search</title>
    <style>
        body { font-family: Arial; margin: 30px; background-color: #f7f9fb; color: #222; }
        input[type=text] { width: 400px; padding: 10px; border-radius: 5px; border: 1px solid #aaa; }
        button { padding: 10px 20px; border: none; background: #007bff; color: white; border-radius: 5px; cursor: pointer; }
        button:hover { background: #0056b3; }
        video { display: block; margin: 20px 0; width: 480px; height: auto; border-radius: 10px; }
    </style>
</head>
<body>
    <h2>🎬 Video Finder</h2>
    <form method="post">
        <input type="text" name="query" placeholder="Enter words or phrases..." required>
        <button type="submit">Search</button>
    </form>
    {% if videos %}
        <h3>Results:</h3>
        <div id="video-container"></div>
        <script>
            const videos = {{ videos|tojson }};
            let current = 0;
            let hasPlayedAll = false;
            let isHandlingEnd = false;

            function playVideo(index) {
                if (hasPlayedAll || index >= videos.length) {
                    hasPlayedAll = true;
                    const container = document.getElementById("video-container");
                    container.innerHTML = "<p><b>✅ All videos played once.</b></p>";
                    return;
                }
                const container = document.getElementById("video-container");
                container.innerHTML = `<p><b>${escapeHtml(videos[index].file_name.replace('.mp4', ''))}</b></p>
                    <video id="videoPlayer" controls autoplay playsinline>
                        <source src="${escapeHtml(videos[index].cloudinary_url)}" type="video/mp4">
                        Your browser does not support the video tag.
                    </video>`;
                
                isHandlingEnd = false;
                const video = document.getElementById("videoPlayer");
                if (!video) return;

                video.addEventListener('ended', function onEnded() {
                    if (isHandlingEnd) return;
                    isHandlingEnd = true;
                    current++;
                    playVideo(current);
                }, { once: true });

                video.addEventListener('error', function onError() {
                    if (isHandlingEnd) return;
                    isHandlingEnd = true;
                    console.warn('Video error at index', index);
                    current++;
                    if (current < videos.length) playVideo(current);
                    else {
                        hasPlayedAll = true;
                        container.innerHTML = "<p><b>✅ All videos played once (some errors occurred).</b></p>";
                    }
                }, { once: true });
            }

            function escapeHtml(str) {
                if (!str) return '';
                return String(str)
                    .replace(/&/g, '&amp;')
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;')
                    .replace(/"/g, '&quot;')
                    .replace(/'/g, '&#039;');
            }

            playVideo(0);
        </script>
    {% elif message %}
        <p><i>{{ message }}</i></p>
    {% endif %}
</body>
</html>
"""



# ---------- Search Function ----------
def search_videos(user_input):
    videos = []
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT file_name, cloudinary_url FROM videos")
    all_videos = cursor.fetchall()
    
    video_dict = {}
    for file_name, url in all_videos:
        normalized_name = file_name.replace('.mp4', '').replace('_', ' ').lower()
        video_dict[normalized_name] = {"file_name": file_name, "cloudinary_url": url}
    
    sorted_names = sorted(video_dict.keys(), key=len, reverse=True)
    
    remaining_input = user_input.lower().strip()
    
    while remaining_input:
        matched = False
        
        for video_name in sorted_names:
            if remaining_input.startswith(video_name):
                videos.append(video_dict[video_name])
                remaining_input = remaining_input[len(video_name):].strip()
                matched = True
                break
        
        if not matched:
            words = remaining_input.split(maxsplit=1)
            current_word = words[0]
            
            # ✅ NEW: Try to spell out the unmatched word letter by letter
            spelled_out = False
            letter_videos = []
            for letter in current_word:
                if letter == ' ':
                    continue
                if letter in video_dict:
                    letter_videos.append(video_dict[letter])
                else:
                    # Even the letter has no video — give up on spelling this word
                    letter_videos = []
                    break
            
            if letter_videos:
                videos.extend(letter_videos)
                spelled_out = True
            
            # Move past this word regardless
            remaining_input = words[1] if len(words) > 1 else ""
    
    cursor.close()
    conn.close()
    
    return videos

# ---------- Web Frontend ----------
@app.route("/", methods=["GET", "POST"])
def index():
    videos = []
    message = ""
    
    if request.method == "POST":
        user_input = request.form["query"].strip().lower()
        
        # --- GEMINI PREPROCESSING STEP ---
        # Everything from here down to the search must be indented
        try:
            
            # print("Attempting to call Gemini 3...")
            
            # The new way to generate content
            response = client.models.generate_content(
                model='gemini-3-flash-preview',
                contents=(
                    f"Strictly fix the spelling of the following text. "
                    f"Rules: 1. Keep word order identical. 2. Do not add words. 3. Do not remove words. "
                    f"Input: '{user_input}'"
                )
            )
            
            # Access the text from the response object
            search_term = response.text.strip().strip('"').strip("'").lower()
            # print(f"SUCCESS! Corrected term: {search_term}")
            
        except Exception as e:
            # print(f"!!! GEMINI ERROR: {e} !!!")
            search_term = user_input.lower()
        # ----------------------------------------------

        videos = search_videos(search_term)
            # print(f"SUCCESS! Corrected term: {search_term}") 
            
               
        if not videos:
            message = f"No match found for '{search_term}'."
            
    return render_template_string(HTML_TEMPLATE, videos=videos, message=message)

# ---------- Mobile API ----------
@app.route("/api/videos", methods=["POST"])
def api_videos():
    data = request.get_json()
    user_input = data.get("query", "").strip()
    
    if not user_input:
        return jsonify({"error": "No query provided"}), 400

    # --- GEMINI PREPROCESSING STEP ---
    try:
        # We prompt Gemini to ONLY return the corrected search term
        response = client.models.generate_content(
                model='gemini-3-flash-preview',
                contents=(
                    f"Strictly fix the spelling of the following text. "
                    f"Rules: 1. Keep word order identical. 2. Do not add words. 3. Do not remove words. "
                    f"Input: '{user_input}'"
                )
            )
        search_term = response.text.strip().lower()
        # print(search_term)
    except Exception as e:
        # Fallback: if Gemini fails, use the original input so the search doesn't break
        # print(f"Gemini Error: {e}")
        search_term = user_input.lower()
    # ---------------------------------
    
    videos = search_videos(search_term)
    
    if not videos:
        return jsonify({"message": f"No matches found for '{search_term}'"}), 404
    
    api_videos = [{"file_name": v["file_name"], "url": v["cloudinary_url"]} for v in videos]
    
    return jsonify({
        "corrected_query": search_term, 
        "videos": api_videos
    })
# # ---------- Local Run ----------
# if __name__ == "__main__":
#     app.run(host="0.0.0.0", port=5000)