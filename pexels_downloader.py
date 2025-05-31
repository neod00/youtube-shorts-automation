"""
Pexels API를 이용한 비디오 다운로더
"""
import os
import requests
import json
import random
import time
import logging
import re
import shutil
from typing import Optional, List, Dict
import urllib.parse
import tempfile
import concurrent.futures
import threading
import queue

# 로깅 설정
logger = logging.getLogger('pexels_downloader')

class PexelsDownloader:
    def __init__(self, api_key=None, progress_callback=None, offline_mode=False):
        """
        Pexels API를 사용하는 비디오 다운로더 초기화
        
        Args:
            api_key: Pexels API 키 (없을 경우 환경 변수나 파일에서 로드 시도)
            progress_callback: 진행 상황 콜백 함수
            offline_mode: 오프라인 모드 활성화 여부
        """
        self.api_key = api_key
        self.progress_callback = progress_callback
        self.offline_mode = offline_mode
        
        # 스레드 안전한 메시지 큐 추가
        self.progress_queue = queue.Queue()
        self.progress_worker_active = False
        
        # API 키가 제공되지 않은 경우 환경 변수나 파일에서 로드 시도
        if not self.api_key:
            self.api_key = self._load_api_key()
            
        self.headers = {"Authorization": self.api_key} if self.api_key else {}
        
        # 환경 설정
        self.temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_videos")
        os.makedirs(self.temp_dir, exist_ok=True)
        
        # 캐시 디렉토리 설정
        self.cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache", "pexels")
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # 백그라운드 비디오 디렉토리 설정
        self.background_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "background_videos")
        os.makedirs(self.background_dir, exist_ok=True)
        
        # 로깅 설정
        self.logger = logging.getLogger('PexelsDownloader')
        
        # requests 모듈 참조 저장
        self.requests = requests
        
        # 캐시된 비디오 목록 (키워드별로 분류)
        self._cached_videos = self._find_cached_videos()
        
        # 메인 스레드인 경우에만 프로그레스 워커 시작
        if threading.current_thread() is threading.main_thread():
            self._start_progress_worker()
        
    def _load_api_key(self):
        """
        API 키 로드 (환경 변수 또는 파일에서)
        """
        # 1. 환경 변수에서 확인
        import os
        api_key = os.environ.get('PEXELS_API_KEY')
        if api_key:
            return api_key
        
        # 2. 설정 파일에서 확인
        try:
            api_settings_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "api_settings.json")
            if os.path.exists(api_settings_path):
                with open(api_settings_path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    if 'pexels_api_key' in settings and settings['pexels_api_key']:
                        return settings['pexels_api_key']
        except Exception as e:
            logger.error(f"API 키 로드 오류: {e}")
        
        # 기본값 반환
        return None
        
    def _find_cached_videos(self) -> Dict[str, List[str]]:
        """임시 디렉토리에서 이미 다운로드된 비디오를 키워드별로 분류"""
        cached_videos = {}
        if os.path.exists(self.temp_dir):
            for file in os.listdir(self.temp_dir):
                if file.startswith("pexels_") and file.endswith(".mp4"):
                    full_path = os.path.join(self.temp_dir, file)
                    if os.path.getsize(full_path) > 0:
                        # 파일명에서 키워드 추출 (pexels_ID_keyword.mp4 형식)
                        keyword_match = re.search(r'pexels_\d+_(.+)\.mp4', file)
                        if keyword_match:
                            keyword = keyword_match.group(1)
                            if keyword not in cached_videos:
                                cached_videos[keyword] = []
                            cached_videos[keyword].append(full_path)
                        else:
                            # 키워드를 추출할 수 없는 경우 'unknown' 카테고리에 추가
                            if 'unknown' not in cached_videos:
                                cached_videos['unknown'] = []
                            cached_videos['unknown'].append(full_path)
        return cached_videos

    def _sanitize_keyword(self, keyword: str) -> str:
        """키워드를 파일명에 안전한 형식으로 변환"""
        return ''.join(c for c in keyword if c.isalnum() or c == '_')

    def _is_korean(self, text: str) -> bool:
        """텍스트가 한국어를 포함하는지 확인"""
        # 한글 유니코드 범위: AC00-D7A3 (가-힣)
        return any('\uAC00' <= char <= '\uD7A3' for char in text)

    def _translate_keyword(self, keyword: str) -> str:
        """한국어 키워드를 영어로 번역"""
        # 이미 영어면 번역 불필요
        if not self._is_korean(keyword):
            return keyword
            
        # 간단한 사전 매핑을 사용한 번역
        kr_to_en = {
            "경제": "economy", "주식": "stock market", "금융": "finance",
            "관세": "tariff", "관세폭탄": "tariff bomb", "무역": "trade",
            "뉴스": "news", "긍정": "positive", "부정": "negative",
            "위기": "crisis", "성장": "growth", "환경": "environment",
            "기후": "climate", "정치": "politics", "선거": "election",
            "여행": "travel", "자연": "nature", "기술": "technology",
            "과학": "science", "우주": "space", "건강": "health",
            "의학": "medicine", "교육": "education", "역사": "history",
            "문화": "culture", "예술": "art", "음악": "music",
            "영화": "movie", "게임": "game", "스포츠": "sports",
            "음식": "food", "요리": "cooking", "패션": "fashion",
            "뷰티": "beauty", "라이프스타일": "lifestyle",
            "겨울": "winter", "눈": "snow", "바다": "sea", "산": "mountain",
            "꽃": "flower", "동물": "animal", "집": "home", "도시": "city",
            "코로나": "covid", "백신": "vaccine", "바이러스": "virus"
        }
        
        # 매칭 시도
        for kr, en in kr_to_en.items():
            if kr in keyword:
                print(f"번역: '{kr}' → '{en}'")
                return en
        
        # 매칭 실패 시 기본값 반환
        return "nature"  # 번역 실패 시 기본값

    def search_videos(self, keyword: str, per_page: int = 15, orientation: str = "portrait") -> List[Dict]:
        """
        Pexels API를 통해 키워드 관련 비디오 검색
        
        Args:
            keyword: 검색 키워드
            per_page: 한 페이지당 결과 수
            orientation: 비디오 방향 (landscape, portrait, square)
            
        Returns:
            List[Dict]: 검색 결과 비디오 목록
        """
        # API 키 검사
        if not self.api_key:
            print("⚠️ Pexels API 키가 설정되지 않았습니다.")
            return []
            
        # 오프라인 모드면 빈 목록 반환
        if self.offline_mode:
            return []
        
        try:
            # 키워드 인코딩
            encoded_keyword = urllib.parse.quote(keyword)
            
            # API URL 구성
            url = f"https://api.pexels.com/videos/search?query={encoded_keyword}&per_page={per_page}&orientation={orientation}"
            print(f"🔍 Pexels 검색 URL: {url}")
            
            print(f"📡 Pexels API 요청 시작...")
            headers = {
                **self.headers,
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            
            response = requests.get(url, headers=headers, timeout=10)  # 10초 타임아웃 설정
            print(f"📡 Pexels API 응답 상태 코드: {response.status_code}")
            
            # API 응답 처리 코드 추가
            if response.status_code == 200:
                data = response.json()
                videos = data.get("videos", [])
                
                print(f"✅ '{keyword}' 검색 결과: {len(videos)}개 비디오 찾음")
                return videos
            else:
                print(f"⚠️ Pexels API 오류: HTTP {response.status_code}")
                print(f"응답: {response.text[:200]}...")
                return []
            
        except Exception as e:
            print(f"⚠️ Pexels API 요청 오류: {str(e)}")
            self.logger.error(f"Pexels API 요청 오류: {str(e)}")
            return []
    
    def _find_cached_videos(self) -> Dict[str, List[str]]:
        """
        캐시 디렉토리에서 키워드별 비디오 파일 목록 찾기
        
        Returns:
            Dict[str, List[str]]: 키워드별 캐시된 비디오 경로 목록
        """
        cached_videos = {}
        
        # 백그라운드 비디오 디렉토리 검색
        if os.path.exists(self.background_dir):
            for filename in os.listdir(self.background_dir):
                if filename.endswith(('.mp4', '.mov', '.avi', '.mkv')):
                    filepath = os.path.join(self.background_dir, filename)
                    
                    # 파일명에서 키워드 추출 (키워드_XXXXX.mp4 형식)
                    parts = filename.split('_')
                    if len(parts) > 1:
                        keyword = parts[0].lower()
                        if keyword not in cached_videos:
                            cached_videos[keyword] = []
                        cached_videos[keyword].append(filepath)
                    
                    # 모든 비디오 "all" 키워드로도 저장
                    if "all" not in cached_videos:
                        cached_videos["all"] = []
                    cached_videos["all"].append(filepath)
                    
        # 캐시 디렉토리도 검색
        if os.path.exists(self.cache_dir):
            for keyword_dir in os.listdir(self.cache_dir):
                keyword_path = os.path.join(self.cache_dir, keyword_dir)
                if os.path.isdir(keyword_path):
                    keyword = keyword_dir.lower()
                    if keyword not in cached_videos:
                        cached_videos[keyword] = []
                        
                    for filename in os.listdir(keyword_path):
                        if filename.endswith(('.mp4', '.mov', '.avi', '.mkv')):
                            filepath = os.path.join(keyword_path, filename)
                            cached_videos[keyword].append(filepath)
                            
                            # 모든 비디오 "all" 키워드로도 저장
                            if "all" not in cached_videos:
                                cached_videos["all"] = []
                            cached_videos["all"].append(filepath)
        
        self.logger.info(f"캐시된 비디오: {len(cached_videos.keys())} 키워드, " + 
                   f"총 {sum(len(videos) for videos in cached_videos.values())}개 파일")
        return cached_videos
    
    def _start_progress_worker(self):
        """메인 스레드에서 진행 상황 업데이트를 처리할 워커 시작"""
        if self.progress_worker_active:
            return  # 이미 실행 중이면 중복 실행 방지
            
        def worker():
            """진행 상황 큐에서 메시지를 처리하는 워커 함수"""
            while True:
                try:
                    # 큐에서 메시지 가져오기
                    message, progress = self.progress_queue.get(timeout=0.5)
                    if message is None:  # 종료 신호
                        break
                        
                    # 콜백이 있으면 메인 스레드에서 안전하게 실행
                    if self.progress_callback:
                        try:
                            if progress is not None:
                                self.progress_callback(message, progress)
                            else:
                                self.progress_callback(message)
                        except Exception as e:
                            self.logger.error(f"진행 상황 콜백 오류: {e}")
                    
                    # 큐 작업 완료 표시
                    self.progress_queue.task_done()
                    
                except queue.Empty:
                    # 타임아웃은 정상이므로 무시
                    continue
                except Exception as e:
                    self.logger.error(f"진행 상황 워커 오류: {e}")
                    
        # 워커 스레드 시작
        self.progress_thread = threading.Thread(target=worker, daemon=True)
        self.progress_thread.start()
        self.progress_worker_active = True
        self.logger.info("진행 상황 워커 스레드 시작됨")
    
    def update_progress(self, text: str, progress: Optional[int] = None):
        """
        스레드 안전한 진행 상황 업데이트
        
        Args:
            text: 표시할 텍스트
            progress: 진행도 (0-100)
        """
        # 로그에는 항상 기록
        self.logger.info(text)
        
        # 콜백이 있는 경우에만 진행 처리
        if self.progress_callback:
            try:
                # 현재 스레드가 메인 스레드인지 확인
                if threading.current_thread() is threading.main_thread():
                    # 메인 스레드에서는 직접 콜백 호출
                    if progress is not None:
                        self.progress_callback(text, progress)
                    else:
                        self.progress_callback(text)
                else:
                    # 백그라운드 스레드에서는 큐에 메시지 추가
                    self.progress_queue.put((text, progress))
            except Exception as e:
                self.logger.error(f"진행 상황 업데이트 오류: {e}")
        else:
            # 콜백이 없는 경우 로그만 남김(위에서 이미 처리됨)
            pass
    
    def _sanitize_keyword(self, keyword: str) -> str:
        """
        키워드를 파일/디렉토리 이름으로 사용할 수 있게 정리
        
        Args:
            keyword: 원본 키워드
            
        Returns:
            str: 정리된 키워드
        """
        # 공백을 밑줄로 대체하고 특수문자 제거
        sanitized = re.sub(r'[^\w\s]', '', keyword.lower()).replace(' ', '_')
        
        # 길이 제한 (파일 시스템 한계 고려)
        if len(sanitized) > 50:
            sanitized = sanitized[:50]
            
        return sanitized
    
    def get_random_video(self, keyword: str, min_duration: float = 0) -> Optional[str]:
        """
        키워드 관련 랜덤 배경 비디오 가져오기
        
        Args:
            keyword: 검색 키워드 (쉼표로 구분된 복수 키워드 가능)
            min_duration: 최소 비디오 길이(초)
            
        Returns:
            Optional[str]: 다운로드된 비디오 파일 경로
        """
        self.update_progress(f"'{keyword}' 관련 배경 비디오 검색 중...", 10)
        
        # 키워드를 개별적으로 분할 (쉼표로 구분된 경우)
        keyword_list = [k.strip() for k in keyword.split(',')]
        if len(keyword_list) > 1:
            self.update_progress(f"검색 키워드 분리: {keyword_list}", 15)
        
        # 1. 오프라인 모드인 경우 캐시에서 검색
        if self.offline_mode:
            self.update_progress("오프라인 모드: 캐시에서 비디오 검색 중...", 20)
            
            # 각 키워드로 캐시 검색 시도
            for idx, single_keyword in enumerate(keyword_list):
                cached_video = self.get_cached_video(single_keyword, min_duration, use_sample_videos=True)
                if cached_video:
                    self.update_progress(f"캐시에서 키워드 '{single_keyword}'로 비디오 발견: {os.path.basename(cached_video)}", 100)
                    return cached_video
            
            # 캐시에 없고 오프라인 모드면 대체 키워드 시도
            fallback_keywords = ["nature", "background", "abstract", "calm", "cinematic"]
            for fallback in fallback_keywords:
                self.update_progress(f"캐시에서 대체 키워드 '{fallback}' 시도...", 30)
                cached_video = self.get_cached_video(fallback, min_duration, use_sample_videos=True)
                if cached_video:
                    self.update_progress(f"대체 키워드로 비디오 발견: {os.path.basename(cached_video)}", 100)
                    return cached_video
            
            self.update_progress("오프라인 모드에서 비디오를 찾을 수 없습니다.", 100)
            return None
        
        # 2. 개별 키워드로 순차적으로 API 검색 시도
        for idx, single_keyword in enumerate(keyword_list):
            # 키워드 변형 (영문 키워드로 변환)
            translated_keyword = self._translate_keyword(single_keyword)
            if translated_keyword != single_keyword:
                self.update_progress(f"번역된 키워드 사용: '{single_keyword}' -> '{translated_keyword}'", 25 + (idx * 5))
                single_keyword = translated_keyword
                
            # API 검색
            self.update_progress(f"Pexels API로 '{single_keyword}' 검색 중...", 30 + (idx * 5))
            videos = self.search_videos(single_keyword)
            
            # 결과가 있고 최소 길이를 충족하는 비디오가 있는지 확인
            if videos and self._has_suitable_duration_video(videos, min_duration):
                # 비디오 다운로드 로직
                return self._process_and_download_video(videos, single_keyword, min_duration)
        
        # 3. 모든 키워드로 검색해도 적절한 결과가 없으면 대체 키워드 시도
        fallback_keywords = ["nature", "background", "abstract", "calm", "cinematic"]
        random.shuffle(fallback_keywords)
        
        for fallback in fallback_keywords:
            if fallback in keyword_list:  # 이미 시도한 키워드는 건너뜀
                continue
                
            self.update_progress(f"적절한 비디오 없음, 대체 키워드 '{fallback}' 시도...", 50)
            videos = self.search_videos(fallback)
            
            if videos and self._has_suitable_duration_video(videos, min_duration):
                return self._process_and_download_video(videos, fallback, min_duration)
        
        # 4. API에서 다운로드 실패한 경우 캐시 확인 (실제 Pexels 비디오 먼저 시도)
        # 각 키워드로 캐시 검색
        for single_keyword in keyword_list:
            self.update_progress(f"API에서 다운로드 실패, 키워드 '{single_keyword}'로 캐시 확인 중...", 70)
            cached_video = self.get_cached_video(single_keyword, min_duration, use_sample_videos=False)
            if cached_video:
                self.update_progress(f"캐시에서 '{single_keyword}' 비디오 발견: {os.path.basename(cached_video)}", 100)
                return cached_video
            
        # 5. 실제 비디오를 찾지 못한 경우 마지막으로 샘플 비디오 시도
        for single_keyword in keyword_list:
            self.update_progress(f"실제 Pexels 비디오를 찾지 못했습니다. 키워드 '{single_keyword}'로 샘플 비디오 확인 중...", 80)
            sample_video = self.get_cached_video(single_keyword, min_duration, use_sample_videos=True)
            if sample_video:
                self.update_progress(f"샘플 비디오 사용: {os.path.basename(sample_video)}", 100)
                return sample_video
        
        # 모든 시도 실패
        self.update_progress(f"'{keyword}' 관련 적절한 비디오를 찾을 수 없습니다.", 100)
        return None
        
    def _process_and_download_video(self, videos: List[Dict], keyword: str, min_duration: float) -> Optional[str]:
        """
        검색 결과 비디오 처리 및 다운로드
        
        Args:
            videos: 검색 결과 비디오 목록
            keyword: 검색 키워드
            min_duration: 최소 비디오 길이(초)
            
        Returns:
            Optional[str]: 다운로드된 비디오 파일 경로
        """
        # 비디오 품질 평가 및 정렬
        videos = self._rank_videos_by_quality(videos)
        
        # 최소 길이 조건이 있으면 필터링
        if min_duration > 0:
            filtered_videos = [v for v in videos if v.get("duration", 0) >= min_duration]
            
            if filtered_videos:
                videos = filtered_videos
                self.update_progress(f"{len(videos)}개의 비디오가 최소 길이 요구사항({min_duration:.1f}초)을 충족합니다.", 55)
            else:
                self.update_progress(f"최소 길이({min_duration:.1f}초)를 충족하는 비디오가 없습니다. 원본 목록 사용.", 55)
        
        # 상위 5개 중에서 무작위 선택
        if videos:
            selected_videos = videos[:min(5, len(videos))]
            selected_video = random.choice(selected_videos)
            
            video_id = selected_video.get("id", "unknown")
            duration = selected_video.get("duration", 0)
            self.update_progress(f"비디오 선택: ID {video_id}, 길이: {duration:.1f}초", 60)
            
            # 최적의 비디오 포맷 선택
            video_files = selected_video.get("video_files", [])
            best_format = self._select_best_video_format(video_files)
            
            if best_format:
                download_url = best_format.get("link")
                if download_url:
                    downloaded_video = self.download_video(download_url, keyword)
                    if downloaded_video:
                        return downloaded_video
        
        return None
    
    def _has_suitable_duration_video(self, videos: List[Dict], min_duration: float) -> bool:
        """
        최소 길이를 충족하는 비디오가 있는지 확인
        
        Args:
            videos: 비디오 정보 목록
            min_duration: 최소 비디오 길이(초)
            
        Returns:
            bool: 적합한 비디오가 있으면 True
        """
        if min_duration <= 0:
            return True
        
        for video in videos:
            duration = video.get("duration", 0)
            if duration >= min_duration:
                return True
                
        return False
    
    def _rank_videos_by_quality(self, videos: List[Dict]) -> List[Dict]:
        """
        비디오를 품질과 관련성에 따라 정렬
        
        Args:
            videos: 비디오 정보 목록
            
        Returns:
            List[Dict]: 정렬된 비디오 목록
        """
        def get_video_score(video):
            # 기본 점수
            score = 0
            
            # 해상도 점수 (높을수록 좋음, 최대 1920)
            width = video.get("width", 0)
            height = video.get("height", 0)
            resolution_score = min(width * height / (1920 * 1080), 1.0) * 5
            score += resolution_score
            
            # 길이 점수 (15-60초가 이상적)
            duration = video.get("duration", 0)
            if 15 <= duration <= 60:
                duration_score = 3
            elif 60 < duration <= 120:
                duration_score = 2
            elif 10 <= duration < 15:
                duration_score = 1
            else:
                duration_score = 0
            score += duration_score
            
            # 품질 표현이 포함된 태그가 있으면 추가 점수
            tags = video.get("tags", [])
            if tags:  # None 체크
                try:
                    tag_text = " ".join(str(tag) for tag in tags if tag is not None).lower()
                    if any(q in tag_text for q in ["hd", "4k", "high quality", "professional"]):
                        score += 2
                except Exception as e:
                    # 태그 처리 중 오류 발생 시 무시
                    self.update_progress(f"태그 처리 중 오류 발생: {str(e)}", None)
            
            return score
            
        # 비디오 정렬
        return sorted(videos, key=get_video_score, reverse=True)
    
    def _select_best_video_format(self, video_files: List[Dict]) -> Optional[Dict]:
        """
        사용 가능한 비디오 포맷 중 최적의 것 선택
        
        Args:
            video_files: 비디오 포맷 목록
            
        Returns:
            Optional[Dict]: 선택된 비디오 포맷
        """
        if not video_files:
            return None
        
        print(f"사용 가능한 비디오 포맷: {len(video_files)}개")
        
        # 세로 비디오 찾기
        portrait_formats = []
        for video_file in video_files:
            if video_file is None:
                continue  # None인 경우 건너뛰기
            
            width = video_file.get("width", 0)
            height = video_file.get("height", 0)
            quality = video_file.get("quality", "")
            file_type = video_file.get("file_type", "")
            
            if quality is None:
                quality = ""
            
            # 세로 비디오 (height > width) 선별
            if height > width:
                print(f"세로형 비디오 발견: {width}x{height}, {quality}, {file_type}")
                portrait_formats.append(video_file)
        
        # 세로 비디오가 없으면 원본 목록 사용
        if not portrait_formats:
            portrait_formats = video_files
        
        # 해상도 기준 정렬
        portrait_formats.sort(key=lambda x: (
            x.get("width", 0) * x.get("height", 0),  # 해상도
            1 if x.get("quality", "").lower() == "hd" else 0  # HD 품질 우선
        ), reverse=True)
        
        # 중간 해상도 선택 (너무 높거나 너무 낮은 해상도 피하기)
        if len(portrait_formats) >= 3:
            # 상위 3개 중에서 중간 해상도 선택
            selected_format = portrait_formats[1]
            print(f"선택된 비디오 포맷: {selected_format.get('width')}x{selected_format.get('height')}, {selected_format.get('quality')}")
        elif portrait_formats:
            # 가장 높은 해상도 선택
            selected_format = portrait_formats[0]
            print(f"선택된 비디오 포맷: {selected_format.get('width')}x{selected_format.get('height')}, {selected_format.get('quality')}")
        else:
            return None
        
        return selected_format
    
    def download_video(self, url: str, keyword: str) -> Optional[str]:
        """
        URL에서 비디오 다운로드
        
        Args:
            url: 다운로드할 비디오 URL
            keyword: 검색 키워드
            
        Returns:
            Optional[str]: 다운로드된 비디오 파일 경로
        """
        if not url:
            self.logger.error("다운로드 URL이 없습니다.")
            self.update_progress("다운로드 URL이 없습니다.", 100)
            return None
            
        # 키워드 정리
        keyword_safe = self._sanitize_keyword(keyword)
        self.update_progress(f"'{keyword}' 관련 비디오 다운로드 시작... URL: {url[:50]}...", 10)
        
        # 임시 파일 생성
        temp_fd, temp_path = tempfile.mkstemp(suffix='.mp4')
        os.close(temp_fd)
        
        try:
            # 스트리밍 다운로드 설정
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            
            self.update_progress(f"Pexels API에서 비디오 다운로드 시작 (URL: {url[:30]}...)", 15)
            with self.requests.get(url, headers=headers, stream=True, timeout=30) as response:
                # 응답 상태 확인 및 로깅
                self.update_progress(f"Pexels API 응답 상태: {response.status_code}", 18)
                response.raise_for_status()
                
                # 파일 크기 확인
                total_size = int(response.headers.get('content-length', 0))
                self.update_progress(f"다운로드할 비디오 크기: {total_size/1024/1024:.2f} MB", 20)
                block_size = 1024  # 1KB
                written = 0
                
                with open(temp_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=block_size):
                        if chunk:
                            f.write(chunk)
                            written += len(chunk)
                            
                            # 진행상황 업데이트 (10% 단위)
                            if total_size > 0:
                                progress = min(20 + int((written / total_size) * 70), 90)
                                progress_pct = int((written / total_size) * 100)
                                if progress_pct % 10 == 0:
                                    self.update_progress(f"다운로드 중... ({progress_pct}%)", progress)
            
            # 다운로드 파일 검사
            if os.path.getsize(temp_path) < 1024:  # 1KB 미만인 경우 오류로 판단
                self.update_progress(f"다운로드된 파일이 너무 작습니다. ({os.path.getsize(temp_path)} bytes)", 100)
                os.remove(temp_path)
                return None
                
            # 다운로드 완료, 캐시에 저장
            self.update_progress(f"다운로드 완료: {os.path.getsize(temp_path)/1024/1024:.2f} MB, 캐시에 저장 중...", 90)
            cache_path = self.save_to_cache(temp_path, keyword_safe)
            
            if cache_path:
                # 임시 파일 삭제
                try:
                    os.remove(temp_path)
                except Exception as e:
                    self.logger.warning(f"임시 파일 삭제 실패: {e}")
                
                self.update_progress(f"비디오 다운로드 성공: {os.path.basename(cache_path)}", 100)
                return cache_path
            else:
                self.update_progress("캐시 저장 실패, 임시 파일 사용", 100)
                return temp_path
                
        except self.requests.exceptions.HTTPError as e:
            self.logger.error(f"HTTP 오류({e.response.status_code}): {e}")
            self.update_progress(f"다운로드 HTTP 오류({getattr(e.response, 'status_code', 'Unknown')}): {e}", 100)
        except self.requests.exceptions.ConnectionError as e:
            self.logger.error(f"연결 오류: {e}")
            self.update_progress(f"다운로드 연결 오류: {e}", 100)
        except self.requests.exceptions.Timeout as e:
            self.logger.error(f"타임아웃 오류: {e}")
            self.update_progress(f"다운로드 타임아웃: {e}", 100)
        except self.requests.exceptions.RequestException as e:
            self.logger.error(f"요청 오류: {e}")
            self.update_progress(f"다운로드 요청 오류: {e}", 100)
        except IOError as e:
            self.logger.error(f"파일 저장 오류: {e}")
            self.update_progress(f"파일 저장 오류: {e}", 100)
        except Exception as e:
            self.logger.error(f"다운로드 중 알 수 없는 오류: {e}")
            self.update_progress(f"다운로드 중 오류 발생: {e}", 100)
            import traceback
            self.logger.error(f"오류 세부 정보: {traceback.format_exc()}")
            
        # 오류 발생 시 임시 파일 삭제
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception as e:
            self.logger.error(f"임시 파일 삭제 오류: {e}")
            
        return None
    
    def get_cached_video(self, keyword: str, min_duration: float = 0, use_sample_videos: bool = False) -> Optional[str]:
        """
        키워드에 해당하는 캐시된 비디오 가져오기
        
        Args:
            keyword: 검색 키워드
            min_duration: 최소 비디오 길이(초)
            use_sample_videos: 샘플 비디오(로컬에서 생성된) 사용 여부
            
        Returns:
            Optional[str]: 캐시된 비디오 파일 경로 (없으면 None)
        """
        keyword_lower = keyword.lower()
        
        # 키워드 정리
        keyword_safe = self._sanitize_keyword(keyword_lower)
        
        # MoviePy 모듈 확인
        has_moviepy = False
        try:
            from moviepy.editor import VideoFileClip
            has_moviepy = True
        except ImportError:
            if min_duration > 0:
                logger.warning("moviepy 라이브러리가 없어 비디오 길이 확인이 불가능합니다.")
        
        # 샘플 비디오 패턴 (이 패턴을 가진 비디오는 필터링됨)
        sample_patterns = ["sample_background", "gradient_background"]
        
        # 실제 Pexels 비디오만 가져올지 결정하는 함수
        def is_valid_video(video_path):
            # use_sample_videos가 True이면 모든 비디오 허용
            if use_sample_videos:
                return True
                
            # 파일명 추출
            filename = os.path.basename(video_path).lower()
            
            # 샘플 패턴이 포함된 파일은 걸러냄
            for pattern in sample_patterns:
                if pattern in filename:
                    return False
                    
            return True
        
        # 1. 직접 매칭 시도
        if keyword_safe in self._cached_videos and self._cached_videos[keyword_safe]:
            valid_videos = [v for v in self._cached_videos[keyword_safe] if is_valid_video(v)]
            
            # 최소 길이 조건이 있고 MoviePy를 사용할 수 있으면 검증
            if min_duration > 0 and has_moviepy:
                suitable_videos = []
                
                for video_path in valid_videos:
                    try:
                        with VideoFileClip(video_path) as clip:
                            if clip.duration >= min_duration:
                                suitable_videos.append(video_path)
                    except Exception:
                        continue
                
                if suitable_videos:
                    return random.choice(suitable_videos)
            elif valid_videos:
                return random.choice(valid_videos)
            
        # 2. 부분 매칭 시도
        partial_matches = []
        for cached_keyword, videos in self._cached_videos.items():
            if (keyword_safe in cached_keyword or cached_keyword in keyword_safe):
                valid_videos = [v for v in videos if is_valid_video(v)]
                
                # 최소 길이 조건이 있으면 검증
                if min_duration > 0 and has_moviepy:
                    for video_path in valid_videos:
                        try:
                            with VideoFileClip(video_path) as clip:
                                if clip.duration >= min_duration:
                                    partial_matches.append(video_path)
                        except Exception:
                            continue
                else:
                    partial_matches.extend(valid_videos)
        
        if partial_matches:
            return random.choice(partial_matches)
                
        # 3. 최소 길이 조건이 있으면 모든 캐시 검색
        if min_duration > 0 and has_moviepy and "all" in self._cached_videos:
            suitable_videos = []
            
            for video_path in self._cached_videos["all"]:
                if not is_valid_video(video_path):
                    continue
                    
                try:
                    with VideoFileClip(video_path) as clip:
                        if clip.duration >= min_duration:
                            suitable_videos.append(video_path)
                except Exception:
                    continue
            
            if suitable_videos:
                logger.info(f"키워드 '{keyword}'에 대한 캐시된 비디오 없음, 최소 길이({min_duration:.1f}초) 이상 무작위 비디오 사용")
                return random.choice(suitable_videos)
        
        # 4. 실제 Pexels 비디오가 없거나 찾지 못한 경우, 샘플 비디오 사용이 허용되면 다시 시도
        if not use_sample_videos:
            logger.info(f"키워드 '{keyword}'에 대한 실제 Pexels 비디오를 찾지 못했습니다. 샘플 비디오 시도...")
            return self.get_cached_video(keyword, min_duration, use_sample_videos=True)
            
        # 5. 길이 조건 없으면 "all" 카테고리에서 무작위 선택 (있는 경우)
        if "all" in self._cached_videos and self._cached_videos["all"]:
            logger.info(f"키워드 '{keyword}'에 대한 캐시된 비디오 없음, 무작위 비디오 사용")
            valid_videos = [v for v in self._cached_videos["all"] if is_valid_video(v)]
            
            if valid_videos:
                return random.choice(valid_videos)
            
        # 캐시된 비디오가 없는 경우
        return None
    
    def save_to_cache(self, video_file: str, keyword: str) -> str:
        """
        비디오 파일을 키워드 기반으로 캐시에 저장
        
        Args:
            video_file: 임시 비디오 파일 경로
            keyword: 검색 키워드
            
        Returns:
            str: 캐시에 저장된 파일 경로
        """
        if not os.path.exists(video_file):
            self.logger.error(f"저장할 비디오 파일이 없습니다: {video_file}")
            return ""
            
        # 키워드 디렉토리 생성
        keyword_safe = self._sanitize_keyword(keyword)
        cache_dir = os.path.join(self.cache_dir, keyword_safe)
        os.makedirs(cache_dir, exist_ok=True)
        
        # 파일명 생성
        timestamp = int(time.time())
        file_ext = os.path.splitext(video_file)[1]
        cache_filename = f"{keyword_safe}_{timestamp}{file_ext}"
        cache_filepath = os.path.join(cache_dir, cache_filename)
        
        # 파일 복사
        try:
            shutil.copy2(video_file, cache_filepath)
            self.logger.info(f"비디오 캐시에 저장됨: {cache_filepath}")
            
            # 캐시 목록 업데이트
            if keyword_safe not in self._cached_videos:
                self._cached_videos[keyword_safe] = []
            self._cached_videos[keyword_safe].append(cache_filepath)
            
            # "all" 카테고리에도 추가
            if "all" not in self._cached_videos:
                self._cached_videos["all"] = []
            self._cached_videos["all"].append(cache_filepath)
            
            return cache_filepath
        except Exception as e:
            self.logger.error(f"비디오 캐시 저장 오류: {e}")
            return video_file  # 실패 시 원본 파일 반환 

    def get_multiple_videos(self, keyword: str, total_duration: float = 60.0, max_videos: int = 5) -> List[str]:
        """
        키워드에 맞는 여러 개의 비디오를 가져와 필요한 총 길이를 만족시킵니다.
        
        Args:
            keyword: 검색 키워드 (쉼표로 구분된 복수 키워드 가능)
            total_duration: 필요한 총 비디오 길이(초)
            max_videos: 최대 비디오 개수
            
        Returns:
            List[str]: 다운로드된 비디오 파일 경로 목록
        """
        self.update_progress(f"'{keyword}' 관련 배경 비디오 {max_videos}개 검색 중...", 10)
        
        # 키워드를 개별적으로 분할 (쉼표로 구분된 경우)
        keyword_list = [k.strip() for k in keyword.split(',')]
        if len(keyword_list) > 1:
            self.update_progress(f"검색 키워드 분리: {keyword_list}", 15)
        
        accumulated_videos = []
        accumulated_duration = 0.0
        
        # 1. 오프라인 모드인 경우 캐시에서만 검색
        if self.offline_mode:
            self.update_progress("오프라인 모드: 캐시에서 비디오 검색 중...", 20)
            
            # 각 키워드로 캐시 검색
            for single_keyword in keyword_list:
                cached_videos = self._find_cached_videos_by_keyword(single_keyword, use_sample_videos=True)
                
                # 캐시에서 찾은 비디오 처리
                for video_path in cached_videos:
                    if len(accumulated_videos) >= max_videos:
                        break
                        
                    # 비디오 길이 확인 (MoviePy 사용)
                    try:
                        from moviepy.editor import VideoFileClip
                        clip = VideoFileClip(video_path)
                        duration = clip.duration
                        clip.close()
                        
                        accumulated_videos.append({
                            "path": video_path,
                            "duration": duration
                        })
                        accumulated_duration += duration
                        
                        if accumulated_duration >= total_duration:
                            break
                    except Exception as e:
                        self.update_progress(f"비디오 길이 확인 실패: {str(e)}", None)
                        continue
                
                if accumulated_duration >= total_duration or len(accumulated_videos) >= max_videos:
                    break
        
        # 2. 온라인 모드인 경우 API 검색
        else:
            # 각 키워드로 검색
            for single_keyword in keyword_list:
                # 키워드 변형 (영문 키워드로 변환)
                translated_keyword = self._translate_keyword(single_keyword)
                if translated_keyword != single_keyword:
                    self.update_progress(f"번역된 키워드 사용: '{single_keyword}' -> '{translated_keyword}'", None)
                    single_keyword = translated_keyword
                
                # API 검색
                self.update_progress(f"Pexels API로 '{single_keyword}' 검색 중...", None)
                videos = self.search_videos(single_keyword)
                
                if not videos:
                    continue
                    
                # 비디오 품질로 정렬
                videos = self._rank_videos_by_quality(videos)
                
                # 필요한 개수의 비디오 다운로드
                for video in videos:
                    if len(accumulated_videos) >= max_videos:
                        break
                        
                    video_id = video.get("id", "unknown")
                    duration = video.get("duration", 0)
                    
                    # 길이가 너무 짧은 비디오는 건너뛰기 (최소 5초)
                    if duration < 5:
                        continue
                    
                    # 비디오 포맷 선택 및 다운로드
                    video_files = video.get("video_files", [])
                    best_format = self._select_best_video_format(video_files)
                    
                    if best_format:
                        download_url = best_format.get("link")
                        if download_url:
                            # 비디오 다운로드
                            video_path = self.download_video(download_url, single_keyword)
                            if video_path:
                                accumulated_videos.append({
                                    "path": video_path,
                                    "duration": duration
                                })
                                accumulated_duration += duration
                                self.update_progress(f"비디오 추가: {os.path.basename(video_path)}, 길이: {duration:.1f}초 (누적: {accumulated_duration:.1f}초)", None)
                                
                                if accumulated_duration >= total_duration:
                                    break
        
        # 3. 로컬 캐시에서 추가 검색 (필요 시)
        if accumulated_duration < total_duration and len(accumulated_videos) < max_videos:
            self.update_progress(f"추가 비디오 필요: 현재 {accumulated_duration:.1f}초/{total_duration:.1f}초", None)
            
            # 일반 키워드로 캐시 검색
            for fallback in ["nature", "background", "abstract", "calm", "cinematic"]:
                if accumulated_duration >= total_duration or len(accumulated_videos) >= max_videos:
                    break
                    
                cached_videos = self._find_cached_videos_by_keyword(fallback, use_sample_videos=True)
                
                for video_path in cached_videos:
                    if len(accumulated_videos) >= max_videos:
                        break
                        
                    # 이미 선택된 비디오인지 확인
                    if any(v["path"] == video_path for v in accumulated_videos):
                        continue
                        
                    # 비디오 길이 확인
                    try:
                        from moviepy.editor import VideoFileClip
                        clip = VideoFileClip(video_path)
                        duration = clip.duration
                        clip.close()
                        
                        accumulated_videos.append({
                            "path": video_path,
                            "duration": duration
                        })
                        accumulated_duration += duration
                        self.update_progress(f"캐시에서 추가 비디오: {os.path.basename(video_path)}, 길이: {duration:.1f}초 (누적: {accumulated_duration:.1f}초)", None)
                        
                        if accumulated_duration >= total_duration:
                            break
                    except Exception as e:
                        self.update_progress(f"비디오 길이 확인 실패: {str(e)}", None)
                        continue
        
        # 결과 변환 및 반환
        result_videos = [v["path"] for v in accumulated_videos]
        
        self.update_progress(f"총 {len(result_videos)}개 비디오 준비 완료, 예상 길이: {accumulated_duration:.1f}초", 100)
        return result_videos

    def _find_cached_videos_by_keyword(self, keyword: str, use_sample_videos: bool = False) -> List[str]:
        """
        캐시에서 키워드에 맞는 비디오 찾기
        
        Args:
            keyword: 검색 키워드
            use_sample_videos: 샘플 비디오도 포함할지 여부
            
        Returns:
            List[str]: 비디오 파일 경로 목록
        """
        result = []
        
        # 키워드 정리
        sanitized_keyword = self._sanitize_keyword(keyword)
        
        # 1. 정확한 매치 먼저 찾기
        # 캐시 디렉토리 확인
        cache_dir = os.path.join(self.cache_dir, sanitized_keyword)
        if os.path.exists(cache_dir):
            for filename in os.listdir(cache_dir):
                if filename.endswith(('.mp4', '.mov', '.avi', '.mkv')):
                    # 샘플 비디오 필터링
                    if not use_sample_videos and ("sample_" in filename or "gradient_background" in filename):
                        continue
                        
                    filepath = os.path.join(cache_dir, filename)
                    result.append(filepath)
        
        # 2. 비슷한 키워드 디렉토리도 검색
        for dirname in os.listdir(self.cache_dir):
            # 이미 검색한 디렉토리는 건너뛰기
            if dirname == sanitized_keyword:
                continue
                
            # 유사성 검사 - 키워드가 디렉토리명에 포함되는지
            if (keyword.lower() in dirname.lower() or
                dirname.lower() in keyword.lower() or
                sanitized_keyword in dirname or
                dirname in sanitized_keyword):
                # 해당 디렉토리의 비디오 파일 추가
                similar_dir = os.path.join(self.cache_dir, dirname)
                if os.path.isdir(similar_dir):
                    for filename in os.listdir(similar_dir):
                        if filename.endswith(('.mp4', '.mov', '.avi', '.mkv')):
                            # 샘플 비디오 필터링
                            if not use_sample_videos and ("sample_" in filename or "gradient_background" in filename):
                                continue
                                
                            filepath = os.path.join(similar_dir, filename)
                            if filepath not in result:  # 중복 방지
                                result.append(filepath)
        
        # 3. 배경 디렉토리 검색
        if os.path.exists(self.background_dir):
            for filename in os.listdir(self.background_dir):
                if filename.endswith(('.mp4', '.mov', '.avi', '.mkv')):
                    # 샘플 비디오 필터링
                    if not use_sample_videos and ("sample_" in filename or "gradient_background" in filename):
                        continue
                        
                    # 키워드가 파일명에 포함되는지 확인
                    if (keyword.lower() in filename.lower() or 
                        sanitized_keyword in filename.lower()):
                        filepath = os.path.join(self.background_dir, filename)
                        if filepath not in result:  # 중복 방지
                            result.append(filepath)
        
        # 4. 전체 키워드 디렉토리 ("all") 확인 - 결과가 적을 때만
        if len(result) < 2:
            all_dir = os.path.join(self.cache_dir, "all")
            if os.path.exists(all_dir) and os.path.isdir(all_dir):
                for filename in os.listdir(all_dir):
                    if filename.endswith(('.mp4', '.mov', '.avi', '.mkv')):
                        # 샘플 비디오 필터링
                        if not use_sample_videos and ("sample_" in filename or "gradient_background" in filename):
                            continue
                            
                        filepath = os.path.join(all_dir, filename)
                        if filepath not in result:  # 중복 방지
                            result.append(filepath)
        
        # 5. 결과가 없을 때 - 샘플/기본 비디오도 포함시키기
        if len(result) == 0 and use_sample_videos:
            # 기본 비디오 검색 (gradient_background, sample 포함)
            for root_dir in [self.cache_dir, self.background_dir, self.temp_dir]:
                if os.path.exists(root_dir):
                    # 루트 디렉토리 내 모든 파일 확인
                    for root, dirs, files in os.walk(root_dir):
                        for filename in files:
                            if filename.endswith(('.mp4', '.mov', '.avi', '.mkv')):
                                if "gradient_background" in filename or "sample_background" in filename:
                                    filepath = os.path.join(root, filename)
                                    if filepath not in result:
                                        result.append(filepath)
        
        # 결과 랜덤화
        if result:
            random.shuffle(result)
            
        return result

    def search_video_links(self, keyword: str, per_page: int = 15) -> List[Dict]:
        """
        키워드 기반 비디오 검색 및 다운로드 URL 추출
        
        Args:
            keyword: 검색할 키워드
            per_page: 페이지당 결과 수
            
        Returns:
            List[Dict]: 비디오 정보 목록 (id, url, width, height, link, keywords)
        """
        videos_info = []
        
        # 오프라인 모드 점검
        if self.offline_mode:
            self.update_progress(f"오프라인 모드: Pexels API 검색 불가", None)
            return videos_info
        
        # 검색 쿼리 설정
        query_keyword = urllib.parse.quote(keyword.strip())
        url = f"https://api.pexels.com/videos/search?query={query_keyword}&per_page={per_page}&orientation=portrait&size=medium"
        
        self.update_progress(f"Pexels API로 '{keyword}' 검색 중...", None)
        
        try:
            # API 키 확인
            if not self.api_key:
                self.update_progress(f"⚠️ Pexels API 키가 설정되지 않았습니다.", None)
                return videos_info
            
            # API 요청
            response = self.requests.get(url, headers=self.headers, timeout=10)
            
            if response.status_code != 200:
                self.update_progress(f"⚠️ Pexels API 오류: {response.status_code}", None)
                return videos_info
            
            data = response.json()
            videos = data.get("videos", [])
            
            # 결과 확인
            if not videos:
                self.update_progress(f"'{keyword}'에 대한 검색 결과가 없습니다.", None)
                return videos_info
            
            self.update_progress(f"'{keyword}'에 대한 {len(videos)}개 결과 검색됨", None)
            
            # 세로 형식 (portrait) 비디오 필터링 
            portrait_videos = []
            for video in videos:
                video_files = video.get("video_files", [])
                
                portrait_files = []
                for vf in video_files:
                    width = vf.get("width", 0)
                    height = vf.get("height", 0)
                    
                    # 세로 비디오 검사 (height > width)
                    if height > width:
                        portrait_files.append(vf)
                
                # 세로 형식 비디오가 있으면 추가
                if portrait_files:
                    # 최적의 품질 선택 (해상도 기준)
                    best_file = max(portrait_files, key=lambda x: x.get("width", 0) * x.get("height", 0))
                    
                    videos_info.append({
                        "id": video.get("id"),
                        "url": best_file.get("link"),
                        "width": best_file.get("width"),
                        "height": best_file.get("height"),
                        "duration": video.get("duration", 0),
                        "preview": video.get("image"),
                        "keyword": keyword  # 검색 키워드 추가
                    })
                
            self.update_progress(f"'{keyword}'에 대한 세로 비디오 {len(portrait_videos)}개 발견", None)
            
            return videos_info
        except Exception as e:
            self.update_progress(f"Pexels API 검색 오류: {str(e)}", None)
            return videos_info

    def batch_search_videos(self, keywords: List[str], per_page: int = 5) -> List[Dict]:
        """
        여러 키워드를 한 번에 검색하고 결과를 취합하여 최적화된 결과 반환
        
        Args:
            keywords: 검색할 키워드 목록
            per_page: 키워드당 결과 수
            
        Returns:
            List[Dict]: 최적화된 통합 검색 결과
        """
        all_videos = []
        
        # API 키 확인
        if not self.api_key or self.offline_mode:
            self.update_progress("API 키가 없거나 오프라인 모드입니다. 검색을 건너뜁니다.", None)
            return []
        
        # 중복 제거 및 최대 5개 키워드로 제한
        unique_keywords = []
        for kw in keywords:
            if kw and kw.lower() not in [k.lower() for k in unique_keywords]:
                unique_keywords.append(kw)
        
        # 키워드 최대 5개로 제한
        if len(unique_keywords) > 5:
            self.update_progress(f"키워드가 너무 많음, 상위 5개만 사용: {unique_keywords[:5]}", None)
            unique_keywords = unique_keywords[:5]
        
        # 각 키워드별로 검색 동시 진행
        def search_keyword(keyword):
            """단일 키워드 검색 함수"""
            self.update_progress(f"'{keyword}' 검색 중...", None)
            videos = self.search_video_links(keyword, per_page)
            return videos
        
        # 쓰레드풀을 사용한 병렬 검색 (최대 3개 동시 실행)
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            future_to_keyword = {executor.submit(search_keyword, kw): kw for kw in unique_keywords}
            
            for future in concurrent.futures.as_completed(future_to_keyword):
                keyword = future_to_keyword[future]
                try:
                    videos = future.result()
                    all_videos.extend(videos)
                    self.update_progress(f"'{keyword}' 검색 완료: {len(videos)}개 결과", None)
                except Exception as e:
                    self.update_progress(f"'{keyword}' 검색 오류: {str(e)}", None)
        
        # 중복 제거 (ID 기준)
        unique_videos = {}
        for video in all_videos:
            video_id = video.get("id")
            if video_id and video_id not in unique_videos:
                unique_videos[video_id] = video
        
        # 비디오 품질 및 관련성 점수 계산
        scored_videos = []
        for video in unique_videos.values():
            score = self._calculate_video_score(video)
            scored_videos.append((score, video))
        
        # 점수 기준 정렬 (내림차순)
        sorted_videos = [v for _, v in sorted(scored_videos, key=lambda x: x[0], reverse=True)]
        
        self.update_progress(f"총 {len(sorted_videos)}개의 고유한 비디오 검색됨", None)
        return sorted_videos

    def _calculate_video_score(self, video: Dict) -> float:
        """
        비디오의 품질과 관련성 점수 계산
        
        Args:
            video: 비디오 정보
            
        Returns:
            float: 품질 점수 (높을수록 좋음)
        """
        score = 0.0
        
        # 1. 해상도 점수 (최대 3점)
        width = video.get("width", 0)
        height = video.get("height", 0)
        
        # 세로 비율 점수 (세로 비디오가 좋음)
        if width > 0 and height > 0:
            aspect_ratio = height / width
            if aspect_ratio >= 1.5:  # 세로형 비디오
                score += 3
            elif aspect_ratio >= 1.0:  # 정사각형
                score += 1.5
            else:  # 가로형 비디오
                score += 0.5
        
        # 2. 길이 점수 (최대 3점)
        duration = video.get("duration", 0)
        if 20 <= duration <= 60:  # 이상적인 길이
            score += 3
        elif 10 <= duration < 20 or 60 < duration <= 120:  # 적당한 길이
            score += 2
        elif 5 <= duration < 10 or 120 < duration <= 180:  # 허용 가능한 길이
            score += 1
        else:  # 너무 짧거나 긴 비디오
            score += 0.5
        
        # 3. HD 품질 추가 점수
        if video.get("height", 0) >= 720:
            score += 1
        
        # 4. 키워드 관련성 (최대 2점)
        video_keyword = video.get("keyword", "").lower()
        if video_keyword in ["nature", "background", "cinematic"]:
            score += 1  # 기본 키워드는 낮은 가중치
        else:
            score += 2  # 사용자 지정 키워드는 높은 가중치
        
        return score

    def get_cached_videos_for_keyword(self, keyword: str) -> List[str]:
        """
        특정 키워드에 관련된 캐시된 비디오 파일 목록 가져오기
        
        Args:
            keyword: 키워드
            
        Returns:
            List[str]: 비디오 파일 경로 목록
        """
        result = []
        
        # 키워드 정리
        safe_keyword = self._sanitize_keyword(keyword)
        
        # 1. 정확한 키워드 매칭
        if safe_keyword in self._cached_videos:
            # 유효한 파일만 추가
            for video_path in self._cached_videos[safe_keyword]:
                if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
                    result.append(video_path)
        
        # 2. 부분 키워드 매칭 시도
        for cache_key, video_paths in self._cached_videos.items():
            # 이미 정확히 일치하는 키워드는 건너뛰기
            if cache_key == safe_keyword:
                continue
            
            # 키워드가 부분적으로 포함된 경우
            if keyword.lower() in cache_key.lower() or cache_key.lower() in keyword.lower():
                for video_path in video_paths:
                    if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
                        # 중복 방지
                        if video_path not in result:
                            result.append(video_path)
        
        # 3. 'all' 카테고리도 확인 (결과가 적을 때만)
        if len(result) < 3 and 'all' in self._cached_videos:
            for video_path in self._cached_videos['all']:
                if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
                    # 중복 방지
                    if video_path not in result:
                        # 비디오 파일명에 키워드가 포함되어 있는지 확인 (더 관련성 높은 결과)
                        filename = os.path.basename(video_path).lower()
                        if (keyword.lower() in filename or safe_keyword in filename or
                            # 비디오가 특정 카테고리에 속하는지 확인
                            any(kw.lower() in filename for kw in [
                                'cityscape', 'abstract', 'business', 'nature', 'technology',
                                'creative', 'art', 'landscape'
                            ])):
                            result.append(video_path)
        
        # 4. 결과가 없을 경우 전체 키워드 목록에서 찾기
        if not result:
            # 디렉토리 기반 검색으로 백업
            result = self._find_cached_videos_by_keyword(keyword, use_sample_videos=False)
            
        # 5. 샘플 비디오도 추가할 필요가 있을 경우
        if not result:
            # gradient_background나 sample 포함 비디오 찾기
            for cache_key, video_paths in self._cached_videos.items():
                for video_path in video_paths:
                    filename = os.path.basename(video_path).lower()
                    if "gradient_background" in filename or "sample_background" in filename:
                        if os.path.exists(video_path) and os.path.getsize(video_path) > 0:
                            if video_path not in result:
                                result.append(video_path)
                                # 최대 3개로 제한
                                if len(result) >= 3:
                                    break
                if len(result) >= 3:
                    break
                    
        # 결과 랜덤화
        if result:
            random.shuffle(result)
            
        return result


class PexelsVideoDownloader(PexelsDownloader):
    """
    Pexels 비디오 다운로더 확장 클래스 
    - VideoCreator 클래스와의 호환성을 위한 인터페이스 제공
    - 기존 PexelsDownloader 클래스의 모든 기능 포함
    """
    
    def __init__(self, api_key=None, progress_callback=None, offline_mode=False):
        """
        PexelsVideoDownloader 초기화
        
        Args:
            api_key: Pexels API 키 (없으면 설정 파일에서 로드)
            progress_callback: 진행 상황 콜백 함수
            offline_mode: 오프라인 모드 활성화 여부
        """
        # API 키가 없으면 설정 파일에서 로드
        if api_key is None:
            try:
                settings_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "api_settings.json")
                with open(settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                api_key = settings.get("pexels_api_key", "")
            except Exception as e:
                logger.error(f"API 설정 로드 오류: {e}")
        
        # 부모 클래스 초기화
        super().__init__(api_key=api_key, progress_callback=progress_callback, offline_mode=offline_mode)
    
    def get_background_video(self, keyword: str, min_duration: float = 0) -> Optional[str]:
        """
        키워드와 최소 길이에 맞는 배경 비디오 가져오기
        get_random_video의 별칭
        
        Args:
            keyword: 검색 키워드
            min_duration: 최소 비디오 길이(초)
            
        Returns:
            Optional[str]: 다운로드된 비디오 파일 경로
        """
        return self.get_random_video(keyword, min_duration=min_duration)
    
    def get_multiple_background_videos(self, keyword: str, required_duration: float, max_videos: int = 3) -> List[Dict]:
        """
        필요한 총 길이를 충족하는 여러 개의 배경 비디오 다운로드
        개선된 버전: 모든 키워드 검색을 한 번에 수행하고 최적의 비디오만 다운로드
        캐시 검색을 건너뛰고 API에서 직접 요청합니다.
        
        Args:
            keyword: 검색 키워드 (쉼표로 구분된 문자열)
            required_duration: 필요한 총 비디오 길이(초)
            max_videos: 최대 다운로드할 비디오 수 (참고용, 길이를 우선시 함)
            
        Returns:
            List[Dict]: 다운로드된 비디오 정보 목록 (path, duration 포함)
        """
        self.update_progress(f"'{keyword}' 관련 배경 비디오 검색 중 (필요 길이: {required_duration:.1f}초)...", 10)
        
        # 키워드를 개별적으로 분할하고 정제
        keyword_list = [k.strip() for k in keyword.split(',')]
        self.update_progress(f"검색 키워드 분리 및 정제: {keyword_list}", 15)
        
        # 결과 저장할 배열
        video_infos = []
        total_duration = 0
        
        # 필요한 길이에 도달했는지 체크하는 함수
        def has_sufficient_duration():
            return total_duration >= required_duration
        
        # API 키 확인
        if not self.api_key or self.offline_mode:
            self.update_progress("API 키가 없거나 오프라인 모드입니다. 대체 비디오 생성을 시도합니다.", 20)
        else:
            # 온라인 모드이고 API 키가 있는 경우 Pexels API 직접 검색
            self.update_progress(f"Pexels API 검색 시작", 25)
            
            # 모든 키워드 합치기
            all_keywords = keyword_list.copy()
            # 기본 키워드 추가
            if len(all_keywords) < 3:
                all_keywords.extend(["nature", "abstract", "cinematic"])
            
            # 키워드 제한 - 너무 많은 키워드는 불필요한 API 호출 발생
            all_keywords = all_keywords[:5]
                
            # 한 번에 통합 검색 - orientation을 명시적으로 "portrait"로 설정
            # 키워드당 결과 수를 축소하여 필요 이상의 결과 방지
            per_page = min(5, max(3, int(10 / len(all_keywords))))
            all_videos = []
            
            # 각 키워드별로 개별 검색 (portrait 명시)
            for idx, single_keyword in enumerate(all_keywords):
                # 이미 충분한 길이에 도달했으면 검색 중단
                if has_sufficient_duration():
                    self.update_progress(f"충분한 비디오를 확보했습니다. 추가 검색 중단.", None)
                    break
                
                self.update_progress(f"키워드 '{single_keyword}' 세로 영상 검색 중...", 30 + (idx * 5))
                videos = self.search_videos(single_keyword, per_page=per_page, orientation="portrait")
                
                if videos:
                    # 키워드 정보 추가
                    for video in videos:
                        if video is not None:  # None 체크 추가
                            video["keyword"] = single_keyword
                    
                    # None이 아닌 비디오만 추가
                    all_videos.extend([v for v in videos if v is not None])
                    self.update_progress(f"'{single_keyword}'로 {len(videos)}개 비디오 찾음", None)
                else:
                    self.update_progress(f"'{single_keyword}'로 세로 비디오를 찾지 못했습니다.", None)
            
            # 세로 비디오가 충분하지 않고 아직 필요한 길이에 도달하지 않았으면 가로 비디오도 추가 검색
            if len(all_videos) < 3 and not has_sufficient_duration():
                self.update_progress(f"세로 비디오가 충분하지 않습니다. 가로 비디오도 검색합니다.", 50)
                for idx, single_keyword in enumerate(all_keywords):
                    # 이미 충분한 길이에 도달했으면 검색 중단
                    if has_sufficient_duration():
                        break
                    
                    landscape_videos = self.search_videos(single_keyword, per_page=per_page, orientation="landscape")
                    if landscape_videos:
                        # 키워드 정보 추가
                        for video in landscape_videos:
                            if video is not None:  # None 체크 추가
                                video["keyword"] = single_keyword
                                video["is_landscape"] = True  # 가로 비디오 표시
                        
                        # None이 아닌 비디오만 추가
                        all_videos.extend([v for v in landscape_videos if v is not None])
                        self.update_progress(f"'{single_keyword}'로 {len(landscape_videos)}개 가로 비디오 찾음", None)
            
            if all_videos:
                self.update_progress(f"총 {len(all_videos)}개 비디오 검색됨, 비디오 다운로드 시작...", 55)
                
                # 중복 제거 (ID 기준)
                unique_videos = {}
                for video in all_videos:
                    # None 체크 및 ID 존재 확인
                    if video is not None and "id" in video:
                        video_id = video.get("id")
                        if video_id and video_id not in unique_videos:
                            unique_videos[video_id] = video
                
                all_videos = list(unique_videos.values())
                self.update_progress(f"중복 제거 후 {len(all_videos)}개 고유한 비디오", None)
                
                # 비디오 품질 평가 및 정렬 (세로 비디오 우선)
                def get_video_score(video):
                    # None 체크
                    if video is None:
                        return -1000  # 최하위 점수
                    
                    # 기본 점수
                    score = 0
                    
                    # 세로 비디오 우선 (가장 중요)
                    is_landscape = video.get("is_landscape", False)
                    if not is_landscape:
                        score += 100  # 세로 비디오에 높은 가중치
                    
                    # 해상도 점수 (높을수록 좋음, 최대 1920)
                    width = video.get("width", 0)
                    height = video.get("height", 0)
                    resolution_score = min(width * height / (1920 * 1080), 1.0) * 5
                    score += resolution_score
                    
                    # 길이 점수 (15-60초가 이상적)
                    duration = video.get("duration", 0)
                    if 15 <= duration <= 60:
                        duration_score = 3
                    elif 60 < duration <= 120:
                        duration_score = 2
                    elif 10 <= duration < 15:
                        duration_score = 1
                    else:
                        duration_score = 0
                    score += duration_score
                    
                    # 품질 표현이 포함된 태그가 있으면 추가 점수
                    tags = video.get("tags", [])
                    if tags:  # None 체크
                        try:
                            tag_text = " ".join(str(tag) for tag in tags if tag is not None).lower()
                            if any(q in tag_text for q in ["hd", "4k", "high quality", "professional"]):
                                score += 2
                        except Exception as e:
                            # 태그 처리 중 오류 발생 시 무시
                            self.update_progress(f"태그 처리 중 오류 발생: {str(e)}", None)
                        
                    return score
                
                # 비디오 정렬 (오류 방지를 위해 예외 처리 추가)
                try:
                    ranked_videos = sorted(all_videos, key=get_video_score, reverse=True)
                except Exception as e:
                    self.update_progress(f"비디오 정렬 중 오류 발생: {str(e)}", None)
                    # 오류 발생시 원래 순서 유지
                    ranked_videos = [v for v in all_videos if v is not None]
                
                # 필요한 길이를 충족하기 위한 최소한의 비디오만 다운로드
                videos_to_download = []
                estimated_duration = 0
                
                for video_info in ranked_videos:
                    # None 체크
                    if video_info is None:
                        continue
                    
                    video_id = video_info.get("id")
                    video_url = None
                    video_keyword = video_info.get("keyword", "nature")
                    video_duration = video_info.get("duration", 0)
                    is_landscape = video_info.get("is_landscape", False)
                    
                    # 비디오 파일 목록 확인
                    video_files = video_info.get("video_files", [])
                    if not video_files:
                        continue
                    
                    # 최적의 비디오 포맷 선택 (is_landscape 플래그 전달)
                    best_format = self._select_best_video_format(video_files, allow_landscape=is_landscape)
                    if best_format:
                        video_url = best_format.get("link")
                    
                    if not video_id or not video_url:
                        continue
                    
                    # 이미 선택한 비디오와 중복 확인
                    is_existing = False
                    for existing in video_infos:
                        existing_path = existing.get("path", "")
                        if existing_path and f"_{video_id}_" in existing_path:
                            is_existing = True
                            break
                    
                    if is_existing:
                        continue
                    
                    # 예상 길이 추가
                    estimated_duration += video_duration
                    
                    # 다운로드할 비디오 목록에 추가
                    videos_to_download.append((video_url, video_keyword, video_id, is_landscape))
                    
                    # 필요한 길이에 도달했는지 확인
                    if estimated_duration >= required_duration:
                        self.update_progress(f"예상 길이({estimated_duration:.1f}초)가 필요한 길이({required_duration:.1f}초)에 도달했습니다. 다운로드 준비 완료.", None)
                        break
                    
                    # 혹시 모를 제한 (최대 5개)
                    if len(videos_to_download) >= 5:
                        self.update_progress(f"다운로드할 최대 비디오 수(5개)에 도달했습니다.", None)
                        break
                
                # 다운로드할 비디오 개수 보고
                if videos_to_download:
                    self.update_progress(f"{len(videos_to_download)}개 비디오 다운로드 시작 (예상 길이: {estimated_duration:.1f}초)...", 60)
                    
                    def download_single_video(args):
                        """단일 비디오 다운로드 함수"""
                        url, kw, vid, is_landscape = args
                        try:
                            return self.download_video(url, kw), kw, vid, is_landscape
                        except Exception as e:
                            self.update_progress(f"비디오 다운로드 내부 오류: {str(e)}", None)
                            return None, kw, vid, is_landscape
                    
                    # ThreadPoolExecutor를 사용한 병렬 다운로드 (최대 3개 동시 실행)
                    downloaded_results = []
                    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                        future_to_video = {executor.submit(download_single_video, args): i for i, args in enumerate(videos_to_download)}
                        
                        completed = 0
                        for future in concurrent.futures.as_completed(future_to_video):
                            completed += 1
                            progress_value = 60 + (completed / len(videos_to_download) * 30)
                            self.update_progress(f"비디오 다운로드 진행 중... ({completed}/{len(videos_to_download)})", progress_value)
                            
                            try:
                                result = future.result()
                                if result[0]:  # downloaded_path가 있는 경우만
                                    downloaded_results.append(result)
                            except Exception as e:
                                self.update_progress(f"비디오 다운로드 결과 처리 오류: {str(e)}", None)
                    
                    # 다운로드 결과 처리
                    self.update_progress(f"{len(downloaded_results)}/{len(videos_to_download)} 비디오 다운로드 완료, 처리 중...", 90)
                    
                    for downloaded_path, kw, vid, is_landscape in downloaded_results:
                        # None 체크
                        if not downloaded_path:
                            continue
                            
                        # 이미 충분한 길이라면 추가 중단
                        if has_sufficient_duration():
                            self.update_progress(f"충분한 길이({total_duration:.1f}초/{required_duration:.1f}초)에 도달했습니다. 추가 비디오 처리 중단.", None)
                            break
                            
                        # 실제 비디오 길이 확인
                        try:
                            from moviepy.editor import VideoFileClip
                            with VideoFileClip(downloaded_path) as clip:
                                actual_duration = clip.duration
                                
                                # 가로 비디오인 경우 정보 추가
                                video_info = {
                                    "path": downloaded_path,
                                    "duration": actual_duration
                                }
                                
                                if is_landscape:
                                    video_info["is_landscape"] = True
                                
                                video_infos.append(video_info)
                                total_duration += actual_duration
                                
                                orientation_text = "가로" if is_landscape else "세로"
                                self.update_progress(f"API에서 받은 {orientation_text} 비디오 추가: {os.path.basename(downloaded_path)}, 길이: {actual_duration:.1f}초 (누적: {total_duration:.1f}초/{required_duration:.1f}초)", None)
                        except Exception as e:
                            self.update_progress(f"다운로드된 비디오 분석 오류: {str(e)}", None)
                            # 오류가 발생한 파일은 건너뛰기
                            continue
        
        # 여전히 충분한 길이가 아니라면, 이미 찾은 비디오를 필요한 만큼 반복 사용
        if total_duration < required_duration and video_infos:
            self.update_progress(f"아직 필요한 길이에 부족함 (현재: {total_duration:.1f}초, 필요: {required_duration:.1f}초), 비디오 반복 사용 설정", 97)
            
            # 비디오를 길이 기준으로 정렬 (가장 긴 것부터)
            sorted_videos = sorted(video_infos, key=lambda x: x.get("duration", 0), reverse=True)
            
            # 가장 긴 비디오 선택 (세로형 비디오 우선)
            portrait_videos = [v for v in sorted_videos if not v.get("is_landscape", False)]
            
            # 세로형 비디오가 있으면 그 중에서 가장 긴 것 선택, 없으면 전체에서 가장 긴 것 선택
            if portrait_videos:
                longest_video = portrait_videos[0]
                self.update_progress(f"반복할 세로형 비디오 선택: {os.path.basename(longest_video.get('path'))}", None)
            else:
                # None 체크 추가
                if sorted_videos:
                    longest_video = sorted_videos[0]
                    self.update_progress(f"세로형 비디오가 없어 가로형 비디오를 반복합니다: {os.path.basename(longest_video.get('path'))}", None)
                else:
                    self.update_progress(f"반복할 비디오가 없습니다. 그라데이션 비디오 생성 시도.", None)
                    longest_video = None
                
            # longest_video가 유효한 경우에만 처리
            if longest_video and "path" in longest_video:
                longest_duration = longest_video.get("duration", 0)
                
                if longest_duration > 0:
                    # 필요한 반복 횟수 계산
                    remaining_duration = required_duration - total_duration
                    repeats_needed = int(remaining_duration / longest_duration) + 1
                    
                    self.update_progress(f"가장 긴 비디오({os.path.basename(longest_video.get('path'))}, {longest_duration:.1f}초)를 {repeats_needed}회 반복하여 부족한 길이({remaining_duration:.1f}초) 채우기", None)
                    
                    # 필요한 만큼 반복 추가
                    for i in range(repeats_needed):
                        # 이미 충분한 길이라면 중단
                        if has_sufficient_duration():
                            break
                        
                        # 반복 사용 정보 추가
                        repeat_info = {
                            "path": longest_video.get("path"),
                            "duration": longest_duration,
                            "is_repeated": True  # 반복 사용 표시
                        }
                        
                        # 가로 비디오인 경우 표시
                        if longest_video.get("is_landscape", False):
                            repeat_info["is_landscape"] = True
                            
                        video_infos.append(repeat_info)
                        
                        total_duration += longest_duration
                        self.update_progress(f"비디오 반복 {i+1}/{repeats_needed} 추가: 누적 {total_duration:.1f}초/{required_duration:.1f}초", None)
        
        # 모든 시도가 실패하면 그라데이션 비디오 생성 (완전히 없는 경우 대비)
        if not video_infos:
            self.update_progress(f"비디오를 찾지 못했습니다. 기본 그라데이션 배경 비디오 생성", 100)
            try:
                from moviepy.editor import ColorClip
                import numpy as np
                from PIL import Image
                
                # 비디오 크기 및 지속 시간 설정
                video_size = (1080, 1920)  # 쇼츠 크기 (세로형)
                
                # 그라데이션 이미지 생성
                gradient_img = Image.new('RGB', video_size)
                pixels = gradient_img.load()
                
                # 블루 그라데이션 기본값
                c1, c2 = (0, 0, 50), (0, 0, 255)
                
                for y in range(video_size[1]):
                    # 수직 그라데이션
                    r = int(c1[0] + (c2[0] - c1[0]) * y / video_size[1])
                    g = int(c1[1] + (c2[1] - c1[1]) * y / video_size[1])
                    b = int(c1[2] + (c2[2] - c1[2]) * y / video_size[1])
                    
                    for x in range(video_size[0]):
                        pixels[x, y] = (r, g, b)
                
                # 임시 파일로 저장
                gradient_img_path = os.path.join(tempfile.gettempdir(), f"gradient_{int(time.time())}.png")
                gradient_img.save(gradient_img_path)
                
                # 이미지를 비디오로 변환 - 캐시 디렉토리 대신 임시 디렉토리에 저장하여 캐시되지 않도록 함
                gradient_video_path = os.path.join(tempfile.gettempdir(), f"gradient_background_{int(time.time())}.mp4")
                
                # ColorClip을 사용하여 비디오 생성
                self.update_progress(f"그라데이션 배경 생성 중... ({required_duration:.1f}초)", None)
                
                # 더미 클립 생성
                clip = ColorClip(video_size, color=(0, 0, 0), duration=required_duration)
                
                # 더미 함수로 프레임 생성
                def make_frame(t):
                    return np.array(Image.open(gradient_img_path))
                
                clip = clip.set_make_frame(make_frame)
                clip.write_videofile(gradient_video_path, fps=24, codec='libx264', audio=False, preset='medium')
                
                # 결과 추가
                video_infos = [{
                    "path": gradient_video_path,
                    "duration": required_duration,
                    "is_generated": True
                }]
                
                self.update_progress(f"기본 그라데이션 배경 비디오 생성 완료: {os.path.basename(gradient_video_path)}", 100)
                
            except Exception as e:
                self.update_progress(f"그라데이션 비디오 생성 실패: {str(e)}", 100)
                import traceback
                self.logger.error(traceback.format_exc())
                
                # 완전히 실패한 경우 빈 배열 반환
                return []
        
        # 최종 결과 요약 및 반환
        self.update_progress(f"배경 비디오 {len(video_infos)}개 준비 완료 (총 {total_duration:.1f}초/{required_duration:.1f}초)", 100)
        
        # 필요한 길이를 확보했는지 최종 확인 메시지
        if total_duration >= required_duration:
            self.update_progress(f"✅ 요청한 길이({required_duration:.1f}초)를 성공적으로 확보했습니다. 실제 길이: {total_duration:.1f}초", 100)
        else:
            self.update_progress(f"⚠️ 요청한 길이({required_duration:.1f}초)를 완전히 확보하지 못했습니다. 실제 길이: {total_duration:.1f}초", 100)
            
        return video_infos
        
    def _select_best_video_format(self, video_files: List[Dict], allow_landscape: bool = False) -> Optional[Dict]:
        """
        사용 가능한 비디오 포맷 중 최적의 것 선택
        
        Args:
            video_files: 비디오 포맷 목록
            allow_landscape: 가로 비디오도 허용할지 여부
            
        Returns:
            Optional[Dict]: 선택된 비디오 포맷
        """
        if not video_files:
            return None
        
        print(f"사용 가능한 비디오 포맷: {len(video_files)}개")
        
        # 세로 비디오 찾기
        portrait_formats = []
        # 가로 비디오 별도로 저장
        landscape_formats = []
        
        for video_file in video_files:
            if video_file is None:
                continue  # None인 경우 건너뛰기
            
            width = video_file.get("width", 0)
            height = video_file.get("height", 0)
            quality = video_file.get("quality", "")
            file_type = video_file.get("file_type", "")
            
            if quality is None:
                quality = ""
            
            # 세로 비디오 (height > width) 선별
            if height > width:
                print(f"세로형 비디오 발견: {width}x{height}, {quality}, {file_type}")
                portrait_formats.append(video_file)
            else:
                print(f"가로형 비디오 발견: {width}x{height}, {quality}, {file_type}")
                landscape_formats.append(video_file)
        
        # 우선 세로 비디오를 사용하려고 시도
        if portrait_formats:
            formats_to_use = portrait_formats
            print(f"{len(portrait_formats)}개의 세로 비디오 포맷 중에서 선택합니다.")
        # 세로 비디오가 없고 가로 비디오 허용 시 가로 비디오 사용
        elif allow_landscape and landscape_formats:
            formats_to_use = landscape_formats
            print(f"세로 비디오가 없어 {len(landscape_formats)}개의 가로 비디오 포맷 중에서 선택합니다.")
        # 모두 없으면 원본 목록 사용
        else:
            formats_to_use = video_files
            print(f"적절한 비디오 포맷을 찾지 못했습니다. 원본 목록 사용: {len(video_files)}개")
        
        # 해상도 기준 정렬
        try:
            formats_to_use.sort(key=lambda x: (
                x.get("width", 0) * x.get("height", 0),  # 해상도
                1 if x.get("quality", "") and x.get("quality", "").lower() == "hd" else 0  # HD 품질 우선
            ), reverse=True)
        except Exception as e:
            print(f"비디오 포맷 정렬 오류: {e}")
            # 오류 발생 시 formats_to_use를 그대로 사용
        
        # 중간 해상도 선택 (너무 높거나 너무 낮은 해상도 피하기)
        if len(formats_to_use) >= 3:
            # 상위 3개 중에서 중간 해상도 선택
            selected_format = formats_to_use[1]
            print(f"선택된 비디오 포맷: {selected_format.get('width')}x{selected_format.get('height')}, {selected_format.get('quality')}")
        elif formats_to_use:
            # 가장 높은 해상도 선택
            selected_format = formats_to_use[0]
            print(f"선택된 비디오 포맷: {selected_format.get('width')}x{selected_format.get('height')}, {selected_format.get('quality')}")
        else:
            return None
        
        return selected_format