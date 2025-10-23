from flask import Flask, request, render_template_string, jsonify
import psycopg2
from psycopg2 import sql
import os
from dotenv import load_dotenv
from flask_cors import CORS



# ---------- Load Environment Variables ----------
load_dotenv()

app = Flask(__name__)
CORS(app, origins="*")  # or restrict to your domain later
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
                container.innerHTML = `
                    <p><b>${escapeHtml(videos[index].file_name)}</b></p>
                    <video id="videoPlayer" controls autoplay playsinline>
                        <source src="${escapeHtml(videos[index].cloudinary_url)}" type="video/mp4">
                        Your browser does not support the video tag.
                    </video>
                `;

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

# ---------- Web Frontend ----------
@app.route("/", methods=["GET", "POST"])
def index():
    videos = []
    message = ""
    
    if request.method == "POST":
        user_input = request.form["query"].strip().lower()
        words = [w.replace(" ", "_") for w in user_input.split()]

        conn = get_connection()
        cursor = conn.cursor()

        for word in words:
            cursor.execute(sql.SQL("SELECT file_name, cloudinary_url FROM videos WHERE file_name ILIKE %s"), [f"%{word}%"])
            result = cursor.fetchone()
            if result:
                videos.append({"file_name": result[0], "cloudinary_url": result[1]})
            else:
                message += f"No match for '{word.replace('_', ' ')}'. "

        cursor.close()
        conn.close()

    return render_template_string(HTML_TEMPLATE, videos=videos, message=message)

# ---------- Mobile API ----------
@app.route("/api/videos", methods=["POST"])
def api_videos():
    data = request.get_json()
    user_input = data.get("query", "").strip().lower()

    if not user_input:
        return jsonify({"error": "No query provided"}), 400

    words = [w.replace(" ", "_") for w in user_input.split()]
    videos = []

    conn = get_connection()
    cursor = conn.cursor()

    for word in words:
        cursor.execute(sql.SQL("SELECT file_name, cloudinary_url FROM videos WHERE file_name ILIKE %s"), [f"%{word}%"])
        result = cursor.fetchone()
        if result:
            videos.append({"file_name": result[0], "url": result[1]})

    cursor.close()
    conn.close()

    if not videos:
        return jsonify({"message": "No matches found"}), 404

    return jsonify({"videos": videos})

# # ---------- Local Run ----------
# if __name__ == "__main__":
#     app.run(host="0.0.0.0", port=5000)
