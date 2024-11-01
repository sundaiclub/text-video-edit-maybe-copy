from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi import FastAPI, File, UploadFile
import shutil
from pathlib import Path
from src.get_audio import extract_audio
from src.word_timestamp import transcribe_audio
from src.get_video_clips import extract_videos
from src.lip_sync import get_lip_sync
from src.voice_cloning import get_cloned_voice
import os
import subprocess
from moviepy.editor import VideoFileClip, concatenate_videoclips
import logging
import json

logging.basicConfig(level=logging.INFO)

app = FastAPI()
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# Define the directory to store the uploaded videos
UPLOAD_DIR = Path("uploaded_videos")
UPLOAD_DIR.mkdir(exist_ok=True)

@app.post("/upload_mp4/")
async def upload_mp4(file: UploadFile = File(...)):
    video_path = UPLOAD_DIR / 'uploaded_video.mp4'

    with video_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    extract_audio(video_path, video_path.with_suffix(".wav"))
    transcribed_audio = transcribe_audio(video_path.with_suffix(".wav"))
    with open(video_path.with_suffix(".json"), "w") as f:
        json.dump(transcribed_audio, f)

    return {"transcription": transcribed_audio}

def time_str_to_seconds(time_str):
    """Convert a timestamp string (HH:MM:SS.sss) to seconds."""
    hours, minutes, seconds = map(float, time_str.split(':'))
    return hours * 3600 + minutes * 60 + seconds


def concat_all_vids(video_directory):
    if not os.path.exists(video_directory):
        logging.error(f"Directory {video_directory} does not exist")
        return

    video_files = [os.path.join(video_directory, f) for f in os.listdir(video_directory) if f.endswith('.mp4')]

    if not video_files:
        logging.error(f"No MP4 files found in {video_directory}")
        return

    video_files.sort()

    with open('videos.txt', 'w') as file:
        for video in video_files:
            file.write(f"file '{video}'\n")

    ffmpeg_command = [
        'ffmpeg',
        '-f', 'concat',
        '-safe', '0',
        '-i', 'videos.txt',
        '-c:v', 'libx264',
        '-strict', '-2',
        'final_output.mp4',
        '-y'
    ]

    try:
        result = subprocess.run(ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            logging.error(f"Error concatenating videos: {result.stderr}")
        else:
            logging.info("Successfully concatenated videos")
    except Exception as e:
        logging.error(f"Error concatenating videos: {str(e)}")


@app.post("/process_script")
def process_script(request: dict):
    original_script = request["original_script"]
    new_script = request["new_script"]    
    to_be_synced = []
    to_be_synced_ids = []
    for _, (old_element, new_element) in enumerate(zip(original_script, new_script)):
        if old_element["start"] == new_element["start"] and old_element["end"] == new_element["end"]:
            if old_element["text"] != new_element["text"]:
                to_be_synced.append({"idx": _, "start": old_element["start"], "end": old_element["end"], "text": new_element["text"]})
                to_be_synced_ids.append(_)
    print('to be synced', to_be_synced_ids)

    final_timestamps = {}
    to_be_synced_ids_map = {}

    start = original_script[0]['start']
    clip = 1
    for i, (org, new) in enumerate(zip(original_script, new_script)):
        if org['start'] == new['start'] and org['end'] == new['end']:
            if org['text'] == new['text']:
                final_timestamps[clip] = (start, org['end'])
            else:
                clip+=1
                final_timestamps[clip] = (new['start'], new['end'])
                to_be_synced_ids_map[clip] = i
                start = new['end']
                clip+=1

    extract_videos('uploaded_videos/uploaded_video.mp4', final_timestamps)

    for i, element in enumerate(to_be_synced):
        idx = element["idx"]
        id_ = to_be_synced_ids_map[idx]
        print('Syncing video', id_)
        text = element["text"]
        get_cloned_voice('uploaded_videos/uploaded_video.wav', id_, text, 'en')
        get_lip_sync(f'videos_output/video_{id_}.mp4', f'voice_cloned_outputs/output_new_{id_}.mp3')
        subprocess.run(['cp', f'lip_sync_outputs/output_new_clip_{id_}.mp4', f'videos_output/video_{id_}.mp4'])

    
    print('org time stamps', to_cut_timestamps)

    concat_all_vids('videos_output')

    return {"message": "Video processed and synced successfully.", "output_video": "final_output.mp4"}



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)