import os
import cloudinary
import cloudinary.uploader
import psycopg2
from psycopg2 import sql
from dotenv import load_dotenv

# Load credentials from .env (for security)
load_dotenv()

# ----------------------------
# 🔧 SET YOUR LOCAL FOLDER PATH HERE
# Example: "D:/MyProjects/Videos" or "./videos"
# ----------------------------
VIDEO_FOLDER = 'C:/Users/Vedant/Desktop/VEDANT/Vedant/college/Characters without logo/day1 season n greetings' # <-- change this to your folder path

# ----------------------------
# ☁️ Cloudinary Configuration
# ----------------------------
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True
)

# ----------------------------
# 🗄️ Neon PostgreSQL Connection
# ----------------------------
conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cursor = conn.cursor()

# Create videos table if it doesn’t exist
cursor.execute("""
    CREATE TABLE IF NOT EXISTS videos (
        id SERIAL PRIMARY KEY,
        file_name VARCHAR(255),
        cloudinary_url TEXT NOT NULL,
        public_id VARCHAR(255),
        uploaded_at TIMESTAMP DEFAULT NOW()
    );
""")
conn.commit()

# ----------------------------
# 🎬 Process Local Videos
# ----------------------------
if not os.path.exists(VIDEO_FOLDER):
    print(f"❌ Folder not found: {VIDEO_FOLDER}")
    exit()

# Get all .mp4 videos in the folder
video_files = [f for f in os.listdir(VIDEO_FOLDER) if f.lower().endswith(".mp4")]

if not video_files:
    print("⚠️ No .mp4 videos found in the folder.")
else:
    print(f"🎬 Found {len(video_files)} videos in '{VIDEO_FOLDER}'. Uploading to Cloudinary...")

for video_file in video_files:
    file_path = os.path.join(VIDEO_FOLDER, video_file)
    print(f"📤 Uploading: {video_file} ...")

    try:
        # Upload to Cloudinary as a video file
        upload_result = cloudinary.uploader.upload(
            file_path,
            resource_type="video"
        )

        cloudinary_url = upload_result.get("secure_url")
        public_id = upload_result.get("public_id")

        # Save metadata in Neon
        cursor.execute(
            sql.SQL("""
                INSERT INTO videos (file_name, cloudinary_url, public_id)
                VALUES (%s, %s, %s)
            """),
            [video_file, cloudinary_url, public_id]
        )
        conn.commit()

        print(f"✅ Uploaded: {video_file}")
        print(f"   🌐 URL: {cloudinary_url}")

    except Exception as e:
        print(f"❌ Error uploading {video_file}: {e}")

cursor.close()
conn.close()
print("🎉 All videos uploaded to Cloudinary and stored in Neon DB successfully!")
