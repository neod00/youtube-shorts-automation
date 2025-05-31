"""
YouTube 업로더 모듈 - Streamlit 버전
"""

import os
import time
import logging
import json
from datetime import datetime
import streamlit as st
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('youtube_uploader')

class YouTubeUploader:
    """YouTube 업로더 클래스 - Streamlit 버전"""
    
    def __init__(self, client_secret_file=None, credentials_file=None, progress_callback=None):
        """
        YouTubeUploader 초기화
        Args:
            client_secret_file: Google API 클라이언트 시크릿 파일 경로
            credentials_file: 저장된 YouTube API 자격 증명 파일 경로
            progress_callback: 진행 상황 콜백 함수 (Streamlit 용)
        """
        self.progress_callback = progress_callback
        self.base_dir = os.path.dirname(os.path.abspath(__file__))

        # 클라이언트 시크릿 파일 설정
        if client_secret_file:
            self.client_secret_file = client_secret_file
        else:
            default_location = os.path.join(self.base_dir, "client_secret.json")
            if os.path.exists(default_location):
                self.client_secret_file = default_location
            else:
                possible_files = [f for f in os.listdir(self.base_dir) if f.startswith("client_secret") and f.endswith(".json")]
                if possible_files:
                    self.client_secret_file = os.path.join(self.base_dir, possible_files[0])
                else:
                    self.client_secret_file = None
                    logger.warning("클라이언트 시크릿 파일을 찾을 수 없습니다.")
        
        # 자격 증명 파일 설정
        if credentials_file:
            self.credentials_file = credentials_file
        else:
            self.credentials_file = os.path.join(self.base_dir, "youtube_credentials.json")
        
        self.youtube = None
        self.authorized = False

    def update_progress(self, message, progress_value=None):
        """진행 상황 업데이트 (Streamlit 사용 시 콜백, 없으면 로그)"""
        if self.progress_callback:
            self.progress_callback(message, progress_value)
        else:
            logger.info(f"{message} ({progress_value if progress_value else ''})")

    def initialize_api(self):
        """YouTube API 초기화 및 인증"""
        try:
            from googleapiclient.discovery import build
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials

            SCOPES = [
                "https://www.googleapis.com/auth/youtube.upload", 
                "https://www.googleapis.com/auth/youtube"
            ]
            self.update_progress("YouTube API 인증 시작...", 10)
            creds = None

            # 저장된 자격 증명 로드
            if os.path.exists(self.credentials_file):
                try:
                    self.update_progress("저장된 인증 정보 로드 중...", 20)
                    with open(self.credentials_file, 'r') as token_file:
                        creds_data = json.load(token_file)
                    creds = Credentials.from_authorized_user_info(creds_data, SCOPES)
                    logger.info("저장된 인증 정보 로드 성공")
                except Exception as e:
                    logger.error(f"저장된 인증 정보 로드 실패: {e}")
                    creds = None

            # 자격 증명이 없거나 유효하지 않은 경우
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    try:
                        self.update_progress("인증 토큰 갱신 중...", 30)
                        creds.refresh(Request())
                        logger.info("인증 토큰 갱신 성공")
                    except Exception as refresh_error:
                        logger.error(f"토큰 갱신 실패: {refresh_error}")
                        creds = None
                if not creds:
                    if not self.client_secret_file or not os.path.exists(self.client_secret_file):
                        error_msg = "클라이언트 시크릿 파일이 없습니다. YouTube API 설정이 필요합니다."
                        logger.error(error_msg)
                        self.update_progress(error_msg, 100)
                        return False
                    self.update_progress("YouTube 계정 인증 필요, 터미널에서 youtube_auth_helper.py 실행!", 40)
                    self.update_progress("""
                    1. cd 프로젝트 경로
                    2. python youtube_auth_helper.py 실행
                    3. Google 인증 → youtube_credentials.json 생성 확인
                    4. 이 앱 새로고침 후 계속 진행
                    """, 50)
                    logger.info(f"수동 인증 필요: {self.client_secret_file}")
                    return False
                try:
                    with open(self.credentials_file, 'w') as token:
                        token.write(creds.to_json())
                    logger.info(f"인증 정보 저장 완료: {self.credentials_file}")
                except Exception as save_error:
                    logger.error(f"인증 정보 저장 실패: {save_error}")

            try:
                self.update_progress("YouTube API 클라이언트 생성 중...", 60)
                self.youtube = build('youtube', 'v3', credentials=creds)
                logger.info("YouTube API 클라이언트 생성 성공")
            except Exception as build_error:
                logger.error(f"API 클라이언트 생성 실패: {build_error}")
                self.update_progress(f"API 클라이언트 생성 실패: {str(build_error)}", 100)
                return False
            try:
                self.update_progress("인증 상태 확인 중...", 70)
                channels_response = self.youtube.channels().list(part='snippet', mine=True).execute()
                if channels_response.get('items'):
                    channel_info = channels_response['items'][0]['snippet']
                    channel_name = channel_info.get('title', '알 수 없음')
                    logger.info(f"인증 성공! 채널: {channel_name}")
                    self.update_progress(f"인증 성공! 채널: {channel_name}", 100)
                    self.authorized = True
                    return True
                else:
                    logger.error("채널 정보를 가져올 수 없습니다. 인증에 문제가 있을 수 있습니다.")
                    self.update_progress("인증에 문제가 있습니다. 채널 정보를 가져올 수 없습니다.", 100)
                    return False
            except Exception as auth_check_error:
                logger.error(f"인증 상태 확인 실패: {auth_check_error}")
                self.update_progress(f"인증 상태 확인 실패: {str(auth_check_error)}", 100)
                return False
        except ImportError as e:
            error_msg = f"Google API 라이브러리가 설치되지 않았습니다: {e}"
            logger.error(error_msg)
            self.update_progress(error_msg, 100)
            return False
        except Exception as e:
            error_msg = f"YouTube API 초기화 중 오류 발생: {e}"
            logger.error(error_msg)
            self.update_progress(error_msg, 100)
            return False

    def upload_video(self, video_file, title, description="", tags=None, category="22",
                    privacy_status="private", is_shorts=True, notify_subscribers=True, thumbnail=None):
        """YouTube에 비디오 업로드"""
        if not self.youtube:
            if not self.initialize_api():
                self.update_progress("YouTube API 인증에 실패했습니다.", 100)
                return None

        self.update_progress("비디오 업로드 준비 중...", 10)
        if not os.path.exists(video_file):
            self.update_progress(f"비디오 파일을 찾을 수 없습니다: {video_file}", 100)
            return None

        tags = tags or []
        # Shorts 태그 자동 추가
        if is_shorts and "#Shorts" not in tags:
            tags.append("#Shorts")
            if "#Shorts" not in description:
                description = "#Shorts\n\n" + description

        media_body = MediaFileUpload(
            video_file, 
            chunksize=1024*1024, 
            resumable=True
        )

        body = {
            'snippet': {
                'title': title,
                'description': description,
                'tags': tags,
                'categoryId': category
            },
            'status': {
                'privacyStatus': privacy_status,
                'selfDeclaredMadeForKids': False,
                'notifySubscribers': notify_subscribers
            }
        }

        try:
            self.update_progress("YouTube API에 업로드 요청 중...", 20)
            upload_request = self.youtube.videos().insert(
                part=','.join(body.keys()),
                body=body,
                media_body=media_body
            )

            response = None
            last_progress = 20
            self.update_progress("YouTube에 업로드 중...", 20)
            while response is None:
                status, response = upload_request.next_chunk()
                if status:
                    progress = int(status.progress() * 100)
                    if progress > last_progress:
                        self.update_progress("YouTube에 업로드 중...", progress)
                        last_progress = progress

            video_id = response['id']
            self.update_progress(f"비디오 업로드 완료! 비디오 ID: {video_id}", 90)

            # 썸네일 업로드
            if thumbnail and os.path.exists(thumbnail):
                self.update_progress("썸네일 업로드 중...", 95)
                try:
                    self.youtube.thumbnails().set(
                        videoId=video_id,
                        media_body=MediaFileUpload(thumbnail)
                    ).execute()
                    self.update_progress("썸네일 업로드 완료", 98)
                except Exception as e:
                    logger.warning(f"썸네일 업로드 실패: {e}")
                    self.update_progress(f"썸네일 업로드 실패: {str(e)}", 98)

            self.update_progress("비디오 업로드 프로세스 완료", 100)
            return video_id

        except HttpError as e:
            try:
                error_content = json.loads(e.content)
                error_message = error_content.get('error', {}).get('message', str(e))
            except Exception:
                error_message = str(e)
            self.update_progress(f"업로드 중 HTTP 오류 발생: {error_message}", 100)
            logger.error(f"YouTube API 오류: {error_message}")
            return None

        except Exception as e:
            self.update_progress(f"업로드 중 오류 발생: {str(e)}", 100)
            logger.error(f"업로드 중 예외 발생: {e}")
            return None

# (app.py에서 사용할 콜백 예시)
def streamlit_progress_callback(message, progress_value=None):
    st.write(message)
    if progress_value is not None:
        st.progress(progress_value)

# (app.py에서는 다음과 같이 인스턴스를 생성)
# youtube_uploader = YouTubeUploader(progress_callback=streamlit_progress_callback)
