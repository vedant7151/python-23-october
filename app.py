from flask import Flask, request, render_template_string, jsonify
import psycopg2
from psycopg2 import sql
import os
from dotenv import load_dotenv
import openai
import tempfile

# ---------- Load Environment Variables ----------
load_dotenv()
app = Flask(__name__)
openai.api_key = os.getenv("OPENAI_API_KEY")


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
                container.innerHTML = `<p><b>${escapeHtml(videos[index].file_name)}</b></p>
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
# ---------- Speech to text ----------
@app.route("/api/audio-to-text", methods=["POST"])
def audio_to_text():
    if "audio" not in request.files:
        return jsonify({"error": "No audio file provided"}), 400

    audio_file = request.files["audio"]

    # Save temporarily
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
        audio_file.save(tmp.name)

        # Whisper API call
        transcript = openai.Audio.transcribe(
            model="whisper-1",
            file=open(tmp.name, "rb")
        )

    raw_text = transcript["text"]

    # ---- minimal processing (same rule as before) ----
    processed_text = " ".join(raw_text.strip().lower().split())

    return jsonify({
        "original_text": raw_text,
        "processed_text": processed_text
    })


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
        videos = search_videos(user_input)
        
        if not videos:
            message = f"No match found for '{user_input}'."
    
    return render_template_string(HTML_TEMPLATE, videos=videos, message=message)

# ---------- Mobile API ----------
@app.route("/api/videos", methods=["POST"])
def api_videos():
    data = request.get_json()
    user_input = data.get("query", "").strip().lower()
    
    if not user_input:
        return jsonify({"error": "No query provided"}), 400
    
    videos = search_videos(user_input)
    
    if not videos:
        return jsonify({"message": "No matches found"}), 404
    
    # Format for API response (using 'url' instead of 'cloudinary_url')
    api_videos = [{"file_name": v["file_name"], "url": v["cloudinary_url"]} for v in videos]
    
    return jsonify({"videos": api_videos})

# # ---------- Local Run ----------
# if __name__ == "__main__":
#     app.run(host="0.0.0.0", port=5000)