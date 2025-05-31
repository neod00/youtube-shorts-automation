"""
YouTube 업로더 모듈 - Streamlit 버전
기존 youtube_uploader_SCU.py를 기반으로 Streamlit 환경에 맞게 최적화됨
"""

import os
import time
import logging
import json
import pickle
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
        
        # 기본 경로 설정
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        
        # 클라이언트 시크릿 파일 설정
        if client_secret_file:
            self.client_secret_file = client_secret_file
        else:
            # 기본 위치에서 찾기
            default_location = os.path.join(self.base_dir, "client_secret.json")
            if os.path.exists(default_location):
                self.client_secret_file = default_location
            else:
                # 파일명 패턴으로 찾기
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
        
        # API 초기화 상태
        self.youtube = None
        self.authorized = False
    
    def update_progress(self, message, progress_value=None):
        """진행 상황 업데이트 (Streamlit 사용 시)"""
        if self.progress_callback:
            self.progress_callback(message, progress_value)
        else:
            logger.info(message)
    
    def initialize_api(self):
        """YouTube API 초기화 및 인증"""
        try:
            # API 라이브러리 가져오기
            from googleapiclient.discovery import build
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            
            # 필요한 권한 범위
            SCOPES = ["https://www.googleapis.com/auth/youtube.upload", 
                     "https://www.googleapis.com/auth/youtube"]
            
            # 인증 진행
            self.update_progress("YouTube API 인증 시작...", 10)
            
            creds = None
            
            # 저장된 자격 증명이 있는지 확인
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
                
                # 새 인증 필요
                if not creds:
                    # 클라이언트 시크릿 파일 확인
                    if not self.client_secret_file or not os.path.exists(self.client_secret_file):
                        error_msg = "클라이언트 시크릿 파일이 없습니다. YouTube API 설정이 필요합니다."
                        logger.error(error_msg)
                        self.update_progress(error_msg, 100)
                        return False
                    
                    # Streamlit 환경에서는 새 인증 과정을 간소화하여 안내
                    self.update_progress("YouTube 계정 인증이 필요합니다. 아래 안내에 따라 수동 인증을 진행해주세요.", 40)
                    
                    # Streamlit 사용자에게 자세한 안내 제공
                    self.update_progress("""
                    1. 명령 프롬프트/터미널에서:
                       - 작업 디렉토리로 이동: cd 경로/SCUstreamlit
                       - 다음 명령어 실행: python youtube_auth_helper.py
                    
                    2. 브라우저가 열리면 Google 계정으로 로그인하고 권한을 허용해주세요.
                    
                    3. 인증이 완료되면 자동으로 youtube_credentials.json 파일이 생성됩니다.
                    
                    4. 인증 후 이 앱을 새로고침하고 다시 시도해주세요.
                    """, 50)
                    
                    # 실제 사용자에게 필요한 정보 제공
                    logger.info(f"수동 인증 필요: 클라이언트 시크릿 파일 = {self.client_secret_file}")
                    return False
                
                # 자격 증명 저장
                try:
                    with open(self.credentials_file, 'w') as token:
                        token.write(creds.to_json())
                    logger.info(f"인증 정보 저장 완료: {self.credentials_file}")
                except Exception as save_error:
                    logger.error(f"인증 정보 저장 실패: {save_error}")
            
            # YouTube API 클라이언트 생성
            try:
                self.update_progress("YouTube API 클라이언트 생성 중...", 60)
                self.youtube = build('youtube', 'v3', credentials=creds)
                logger.info("YouTube API 클라이언트 생성 성공")
            except Exception as build_error:
                logger.error(f"API 클라이언트 생성 실패: {build_error}")
                self.update_progress(f"API 클라이언트 생성 실패: {str(build_error)}", 100)
                return False
            
            # 인증 확인
            try:
                self.update_progress("인증 상태 확인 중...", 70)
                # 간단한 API 호출로 인증 확인
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
        """
        YouTube에 비디오 업로드
        
        Args:
            video_file: 업로드할 비디오 파일 경로
            title: 비디오 제목
            description: 비디오 설명
            tags: 태그 목록
            category: 비디오 카테고리 ID
            privacy_status: 공개 상태 (public, private, unlisted)
            is_shorts: Shorts 동영상 여부
            notify_subscribers: 구독자에게 알림 여부
            thumbnail: 썸네일 이미지 파일 경로
            
        Returns:
            업로드된 비디오 ID
        """
        if not self.youtube:
            if not self.initialize_api():
                self.update_progress("YouTube API 인증에 실패했습니다.", 100)
                return None

        self.update_progress("비디오 업로드 준비 중...", 10)
        
        if not os.path.exists(video_file):
            self.update_progress(f"비디오 파일을 찾을 수 없습니다: {video_file}", 100)
            return None
            
        tags = tags or []
        
        # Shorts 비디오인 경우 #Shorts 태그 추가
        if is_shorts and "#Shorts" not in tags:
            tags.append("#Shorts")
            
            # 설명에도 #Shorts 추가
            if "#Shorts" not in description:
                description = "#Shorts\n\n" + description
        
        # 미디어 파일 정보
        media_body = MediaFileUpload(
            video_file, 
            chunksize=1024*1024, 
            resumable=True
        )
        
        # 비디오 메타데이터
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
            
            # 업로드 요청 생성
            upload_request = self.youtube.videos().insert(
                part=','.join(body.keys()),
                body=body,
                media_body=media_body
            )
            
            # 업로드 진행 상황 모니터링
            response = None
            # 업로드 시작 메시지를 한 번만 출력
            self.update_progress("YouTube에 업로드 중...", 20)
            
            # 업로드 진행 상황을 추적
            last_progress = 20  # 초기값
            while response is None:
                status, response = upload_request.next_chunk()
                if status:
                    progress = int(status.progress() * 100)
                    # 진행률이 변경되었을 때만 업데이트
                    if progress > last_progress:
                        # 진행률만 업데이트 (메시지는 항상 동일하게 유지)
                        if self.progress_callback:
                            self.progress_callback("YouTube에 업로드 중...", progress)
                        else:
                            logger.info(f"YouTube 업로드 진행 중: {progress}%")
                        last_progress = progress
            
            video_id = response['id']
            self.update_progress(f"비디오 업로드 완료! 비디오 ID: {video_id}", 90)
            
            # 썸네일 업로드 (제공된 경우)
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
            error_content = json.loads(e.content)
            error_message = error_content.get('error', {}).get('message', str(e))
            self.update_progress(f"업로드 중 HTTP 오류 발생: {error_message}", 100)
            logger.error(f"YouTube API 오류: {error_message}")
            return None
            
        except Exception as e:
            self.update_progress(f"업로드 중 오류 발생: {str(e)}", 100)
            logger.error(f"업로드 중 예외 발생: {e}")
            return None 