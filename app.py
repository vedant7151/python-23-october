from flask import Flask, request, render_template_string, jsonify
import psycopg2
from psycopg2 import sql
import os
from dotenv import load_dotenv
# import openai
import google.generativeai as genai
from flask import Flask, request, jsonify
# import tempfile

# ---------- Load Environment Variables ----------
load_dotenv()
app = Flask(__name__)
# openai.api_key = os.getenv("OPENAI_API_KEY")

genai.configure(api_key="AIzaSyCXt4oF_IkpK6jFtM8HYN72RJMyeScZogU")
model = genai.GenerativeModel('gemini-3-flash-preview')


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

# @app.route("/api/audio-to-text", methods=["POST"])
# def audio_to_text():
#     if "audio" not in request.files:
#         return jsonify({"error": "No audio file provided"}), 400

#     audio_file = request.files["audio"]
    
#     # 1. Get the original extension (e.g., .m4a)
#     _, ext = os.path.splitext(audio_file.filename)
#     if not ext:
#         ext = ".m4a" # Default fallback

#     # 2. Use the correct suffix so OpenAI knows the format
#     with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
#         audio_file.save(tmp)
#         tmp_path = tmp.name

#     try:
#         # 3. Open the saved file and transcribe
#         with open(tmp_path, "rb") as f:
#             transcript = openai.Audio.transcribe(
#                 model="whisper-1",
#                 file=f
#             )
        
#         raw_text = transcript["text"]
#         processed_text = " ".join(raw_text.strip().lower().split())

#         return jsonify({
#             "original_text": raw_text,
#             "processed_text": processed_text
#         })
#     except Exception as e:
#         print(f"Transcription Error: {e}")
#         return jsonify({"error": str(e)}), 500
#     finally:
#         # 4. Clean up the temp file manually since we used delete=False
#         if os.path.exists(tmp_path):
#             os.remove(tmp_path)

# ---------- Search Function ----------
def search_videos(user_input):
    """
    Search for videos by matching phrases in the input sentence.
    Tries to find the longest matching phrases first (greedy approach).
    """
    videos = []
    conn = get_connection()
    cursor = conn.cursor()
    
    # Get all video names from database for matching
    cursor.execute("SELECT file_name, cloudinary_url FROM videos")
    all_videos = cursor.fetchall()
    
    # Create a dictionary of normalized names -> video data
    video_dict = {}
    for file_name, url in all_videos:
        # Remove .mp4 extension and convert underscores to spaces for matching
        normalized_name = file_name.replace('.mp4', '').replace('_', ' ').lower()
        video_dict[normalized_name] = {"file_name": file_name, "cloudinary_url": url}
    
    # Sort video names by length (longest first) for greedy matching
    sorted_names = sorted(video_dict.keys(), key=len, reverse=True)
    
    # Process the input sentence
    remaining_input = user_input.lower().strip()
    
    while remaining_input:
        matched = False
        
        # Try to match the longest possible phrase from the beginning
        for video_name in sorted_names:
            if remaining_input.startswith(video_name):
                # Found a match!
                videos.append(video_dict[video_name])
                # Remove the matched part and any trailing spaces
                remaining_input = remaining_input[len(video_name):].strip()
                matched = True
                break
        
        if not matched:
            # No match found for current position, skip one word
            words = remaining_input.split(maxsplit=1)
            if len(words) > 1:
                remaining_input = words[1]
            else:
                break  # No more words to process
    
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
            prompt = (
                f"Strictly fix the spelling of the following text. "
                f"Rules: 1. Keep word order identical. 2. Do not add words. 3. Do not remove words. "
                f"Input: '{user_input}'"
            )
            # print("Attempting to call Gemini...") # Add this to see if it starts
            
            response = model.generate_content(prompt)
            search_term = response.text.strip().strip('"').strip("'").lower()
            
            # print(f"SUCCESS! Corrected term: {search_term}") 
            
        except Exception as e:
            # THIS IS WHERE YOUR ERROR MESSAGE WILL SHOW UP
            # print("\n!!! GEMINI ERROR DETECTED !!!")
            # print(f"Error details: {e}") 
            # print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n")
            
            search_term = user_input.lower()
        
        # --- SEARCH STEP ---
        videos = search_videos(search_term)
        
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
        prompt = (
        f"Strictly fix the spelling of the following text. "
        f"Rules: 1. Keep word order identical. 2. Do not add words. 3. Do not remove words. "
        # f"Example: 'howe are you' -> 'how are you'. "
        # f"Example: 'howe are  you hood morningds' -> 'how are you good morning'. "
        f"Input: '{user_input}'"
    )
        response = model.generate_content(prompt)
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