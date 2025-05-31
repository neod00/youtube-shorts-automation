"""
Jamendo API를 사용한 음악 제공자 모듈
"""
import os
import json
import requests
import random
import time
from typing import Optional, List, Dict, Any
# googletrans 라이브러리 제거 (호환성 문제 해결)
# from googletrans import Translator

class JamendoMusicProvider:
    """Jamendo API를 사용하여 음악 검색 및 다운로드 - YouTube 자동화 프로그램용"""
    
    def __init__(self, client_id: str = "a9d56059", output_dir: str = "background_music", 
                 progress_callback = None, cache_dir: str = None, pexels_downloader = None):
        """
        Jamendo API 초기화
        
        Args:
            client_id: Jamendo API 클라이언트 ID
            output_dir: 다운로드 음악을 저장할 디렉토리
            progress_callback: 진행 상황 업데이트 콜백 함수
            cache_dir: 캐시 저장 디렉토리 (기본값: output_dir)
            pexels_downloader: 번역 기능을 위한 PexelsDownloader 객체
        """
        self.client_id = client_id
        self.api_base = "https://api.jamendo.com/v3.0"
        self.output_dir = output_dir
        self.progress_callback = progress_callback
        
        # 캐시 디렉토리 설정
        if cache_dir:
            self.cache_dir = cache_dir
            os.makedirs(self.cache_dir, exist_ok=True)
        else:
            self.cache_dir = output_dir
            
        self.cache_file = os.path.join(self.cache_dir, "jamendo_cache.json")
        
        # 다운로드 디렉토리 생성
        os.makedirs(output_dir, exist_ok=True)
        
        # 캐시 초기화
        self.cache = self._load_cache()
        
        # 오프라인 모드 감지
        self.offline_mode = False
        self._check_connection()
        
        # Pexels 다운로더 참조 (번역 기능을 위해)
        self.pexels_downloader = pexels_downloader
        
        # GoogleTrans 번역기를 사용하지 않고 단어 사전을 활용
        self.kr_to_en = {
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
            "코로나": "covid", "백신": "vaccine", "바이러스": "virus",
            "행복": "happiness", "슬픔": "sadness", "차분": "calm", "편안": "relaxing",
            "활기찬": "energetic", "즐거운": "joyful", "명상": "meditation"
        }
    
    def _check_connection(self):
        """인터넷 연결 확인"""
        try:
            # Google의 DNS 서버로 연결 시도
            import socket
            socket.create_connection(("8.8.8.8", 53), timeout=3)
            self.offline_mode = False
            self._update_progress("온라인 모드로 Jamendo API 초기화")
        except:
            self.offline_mode = True
            self._update_progress("오프라인 모드로 Jamendo API 초기화")
    
    def _update_progress(self, message, progress=None):
        """진행 상황 업데이트"""
        if self.progress_callback:
            if progress is not None:
                self.progress_callback(message, progress)
            else:
                self.progress_callback(message)
        else:
            print(message)
    
    def _load_cache(self) -> Dict:
        """캐시 파일 로드"""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠️ 캐시 파일 로드 실패: {str(e)}")
        return {"keywords": {}, "downloads": {}}
    
    def _save_cache(self):
        """캐시 파일 저장"""
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ 캐시 파일 저장 실패: {str(e)}")
    
    def translate_to_english(self, text: str) -> str:
        """Translate Korean text to English for better API results"""
        try:
            # Check if text contains Korean characters
            if any(ord(char) >= 0xAC00 and ord(char) <= 0xD7A3 for char in text):
                # 사전 기반 번역 방식 사용
                for kr, en in self.kr_to_en.items():
                    if kr in text:
                        print(f"🔤 '{kr}'를 '{en}'로 번역했습니다")
                        return en
                        
                # 매칭 실패 시 Pexels 다운로더의 번역 기능 활용
                if self.pexels_downloader and hasattr(self.pexels_downloader, 'translate_to_english'):
                    try:
                        return self.pexels_downloader.translate_to_english(text)
                    except:
                        pass
                        
                # 모든 번역 시도 실패 시 기본값 반환
                return "calm" 
        except Exception as e:
            print(f"⚠️ 번역 오류: {str(e)}")
        return text
    
    def search_music(self, keyword: str, limit: int = 10, use_cache: bool = True) -> List[Dict[str, Any]]:
        """
        키워드로 음악 검색
        
        Args:
            keyword: 검색 키워드
            limit: 반환할 결과 수
            use_cache: 캐시 사용 여부
            
        Returns:
            List[Dict]: 검색 결과 목록
        """
        # Translate Korean keywords to English for better results
        english_keyword = self.translate_to_english(keyword)
        cache_key = f"{english_keyword}_{limit}"
        
        # 캐시 확인
        if use_cache and "keywords" in self.cache and cache_key in self.cache["keywords"]:
            cache_data = self.cache["keywords"][cache_key]
            cache_time = cache_data.get("time", 0)
            # 캐시가 7일 이내인 경우에만 사용하고, 결과가 있는 경우에만 캐시 사용
            if time.time() - cache_time < 7 * 24 * 60 * 60 and len(cache_data.get("results", [])) > 0:
                print(f"✅ 캐시에서 '{english_keyword}' 검색 결과 로드")
                return cache_data.get("results", [])
        
        # API 문서에 맞게 기본 URL 형식 사용
        endpoint = f"{self.api_base}/tracks/"
        
        # 필수 파라미터만 사용 (성공률 향상)
        params = {
            "client_id": self.client_id,
            "format": "json",
            "limit": limit * 2,  # 필터링을 위해 더 많은 결과 요청
            "search": english_keyword,  # 검색 키워드
            "boost": "popularity_total",  # 인기도 기준 정렬
            "include": "musicinfo",  # BPM 정보 포함
            "vocalinstrumental": "instrumental"  # 가사 없는 음악만 (모든 검색에 적용)
        }
        
        try:
            print(f"🔍 Jamendo API로 '{english_keyword}' 검색 중...")
            
            response = requests.get(endpoint, params=params)
            
            # 상태 코드 확인
            print(f"📥 응답 상태 코드: {response.status_code}")
            
            if response.status_code != 200:
                print(f"⚠️ API 응답 오류: {response.status_code}, {response.text[:100]}")
                return []
                
            data = response.json()
            
            # 디버깅을 위해 응답의 일부 출력
            if "headers" in data:
                if data.get("headers", {}).get("status") == "failed":
                    print(f"⚠️ API 오류: {data.get('headers', {}).get('error_message', '알 수 없는 오류')}")
                    return []
            
            # API 응답 검사
            if "results" not in data:
                print(f"⚠️ API 응답에 'results' 필드가 없습니다.")
                return []
                
            results = data.get("results", [])
            
            # 검색 결과 개수 출력
            results_count = len(results)
            print(f"✅ '{english_keyword}' 검색 결과: {results_count}개 트랙 발견")
            
            # 결과가 없으면 빈 리스트 반환
            if results_count == 0:
                print(f"⚠️ '{keyword}' 검색 결과가 없습니다.")
                return []
            
            # 트랙 필터링: 제목/설명에 우울한 키워드가 있는 트랙 제외
            filtered_results = []
            negative_keywords = ["sad", "dark", "melancholy", "depressing", "gloomy", "grief", 
                               "sorrow", "painful", "despair", "heartbreak", "darkness", 
                               "깊은", "어두운", "슬픈", "우울한", "처절한"]
            
            for track in results:
                # 부정적인 키워드 확인
                track_name = track.get("name", "").lower()
                track_tags = " ".join(track.get("tags", [])).lower()
                
                # 부정적인 키워드가 있는지 확인
                is_negative = False
                for neg_word in negative_keywords:
                    if neg_word in track_name or neg_word in track_tags:
                        is_negative = True
                        print(f"⚠️ 부정적인 키워드가 포함된 트랙 제외: {track.get('name')}")
                        break
                
                # BPM이 너무 낮은 경우 제외 (BPM 정보가 있는 경우)
                if "musicinfo" in track and "bpm" in track["musicinfo"]:
                    bpm = float(track["musicinfo"]["bpm"])
                    if bpm < 70:  # 70 BPM 미만은 너무 느림
                        is_negative = True
                        print(f"⚠️ 템포가 너무 느린 트랙 제외: {track.get('name')} (BPM: {bpm})")
                
                if not is_negative:
                    # 다운로드 URL 추가
                    track_id = track.get("id")
                    if track_id:
                        track["audiodownload"] = f"https://mp3d.jamendo.com/?trackid={track_id}&format=mp32&from=app-{self.client_id}"
                    filtered_results.append(track)
            
            # 결과가 limit보다 많으면 잘라내기
            if len(filtered_results) > limit:
                filtered_results = filtered_results[:limit]
            
            # 필터링 전후 결과 수 비교
            print(f"🔍 원본 결과: {results_count}개, 필터링 후: {len(filtered_results)}개")
            
            # 결과가 있을 때만 캐시에 저장
            if filtered_results:
                if "keywords" not in self.cache:
                    self.cache["keywords"] = {}
                self.cache["keywords"][cache_key] = {
                    "time": time.time(),
                    "results": filtered_results
                }
                self._save_cache()
            
            return filtered_results
                
        except Exception as e:
            print(f"❌ Jamendo 검색 오류: {str(e)}")
            import traceback
            traceback.print_exc()
            return []
    
    def download_track(self, track_info: Dict[str, Any]) -> Optional[str]:
        """
        트랙 정보를 기반으로 음악 다운로드
        
        Args:
            track_info: Jamendo API로부터 받은 트랙 정보
            
        Returns:
            Optional[str]: 다운로드된 파일 경로 또는 None
        """
        if not track_info:
            print("⚠️ 유효하지 않은 트랙 정보")
            return None
            
        track_id = track_info.get("id")
        if not track_id:
            print("⚠️ 트랙 ID가 없습니다")
            return None
            
        # 다운로드 URL이 없으면 생성
        if "audiodownload" not in track_info:
            track_info["audiodownload"] = f"https://mp3d.jamendo.com/?trackid={track_id}&format=mp32&from=app-{self.client_id}"

        try:
            # 캐시 확인
            if "downloads" in self.cache and str(track_id) in self.cache["downloads"]:
                cached_path = self.cache["downloads"][str(track_id)]["path"]
                if os.path.exists(cached_path):
                    print(f"✅ 이미 다운로드된 트랙: {os.path.basename(cached_path)}")
                    return cached_path
            
            # 아티스트와 트랙명으로 파일명 생성
            artist = track_info.get("artist_name", "unknown").replace("/", "_").replace("\\", "_")
            name = track_info.get("name", "unknown").replace("/", "_").replace("\\", "_")
            filename = f"{artist}_-_{name}_{track_id}.mp3"
            
            # 특수문자 필터링
            invalid_chars = '<>:"|?*'
            for char in invalid_chars:
                filename = filename.replace(char, '_')
            
            output_path = os.path.join(self.output_dir, filename)
            
            # 이미 존재하는지 확인
            if os.path.exists(output_path):
                # 캐시 업데이트
                if "downloads" not in self.cache:
                    self.cache["downloads"] = {}
                self.cache["downloads"][str(track_id)] = {
                    "path": output_path,
                    "artist": artist,
                    "name": name,
                    "timestamp": time.time()
                }
                self._save_cache()
                return output_path

            download_url = track_info["audiodownload"]
            print(f"📥 트랙 다운로드 중: {artist} - {name}")
            print(f"   다운로드 URL: {download_url}")

            # 헤더 추가 (레퍼러 및 User-Agent)
            headers = {
                "Referer": "https://www.jamendo.com/",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }

            response = requests.get(download_url, headers=headers, stream=True)
            
            # 응답 확인
            if response.status_code != 200:
                print(f"⚠️ 다운로드 실패: 상태 코드 {response.status_code}")
                print(f"   응답: {response.text[:100]}")
                return None
                
            # 콘텐츠 타입 확인
            content_type = response.headers.get('Content-Type', '')
            print(f"   콘텐츠 타입: {content_type}")
            
            if 'audio' not in content_type and 'application/octet-stream' not in content_type:
                print(f"⚠️ 유효한 오디오 파일이 아닙니다: {content_type}")
                return None
            
            # 다운로드 진행 상황 표시
            total_size = int(response.headers.get('content-length', 0))
            block_size = 8192
            downloaded = 0
            
            with open(output_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=block_size):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        # 다운로드 진행률 표시 (10% 단위)
                        if total_size > 0:
                            progress = int(50 * downloaded / total_size)
                            percent = int(100 * downloaded / total_size)
                            
                            if percent % 10 == 0 and percent > 0:
                                bar = '█' * progress + '░' * (50 - progress)
                                print(f"\r   다운로드 진행률: |{bar}| {percent}% ", end='')
            
            print()  # 진행률 표시 후 줄바꿈

            file_size = os.path.getsize(output_path)
            if file_size < 10000:  # 10KB 미만이면 실패로 간주
                os.remove(output_path)
                print(f"❌ 다운로드된 파일이 너무 작습니다 ({file_size} bytes)")
                return None

            print(f"✅ 트랙 다운로드 완료: {output_path} ({file_size / 1024 / 1024:.2f}MB)")
            
            # 캐시에 다운로드 정보 추가
            if "downloads" not in self.cache:
                self.cache["downloads"] = {}
            self.cache["downloads"][str(track_id)] = {
                "path": output_path,
                "artist": artist,
                "name": name,
                "size": file_size,
                "timestamp": time.time()
            }
            self._save_cache()
            
            return output_path

        except Exception as e:
            print(f"❌ 트랙 다운로드 오류: {str(e)}")
            import traceback
            traceback.print_exc()
            return None
    
    def search_with_fallback(self, keyword: str, limit: int = 10, use_cache: bool = True) -> List[Dict[str, Any]]:
        """
        콤마로 구분된 키워드를 개별적으로 검색하여 첫 번째 결과가 있는 키워드 사용
        
        Args:
            keyword: 검색 키워드 (콤마로 구분된 복수 키워드 가능)
            limit: 반환할 결과 수
            use_cache: 캐시 사용 여부
            
        Returns:
            List[Dict]: 검색 결과 목록
        """
        # 키워드가 없으면 빈 리스트 반환
        if not keyword:
            print("⚠️ 검색 키워드가 비어 있습니다")
            return []
            
        # 콤마로 구분된 키워드를 분리하고 공백 제거
        keywords = [k.strip() for k in keyword.split(',') if k.strip()]
        
        # 키워드가 없거나 분리되지 않았으면 원래 키워드 사용
        if not keywords:
            keywords = [keyword]
            
        print(f"🔍 검색할 키워드 목록: {keywords}")
        
        # 한국어 키워드가 있을 경우 영어로 번역
        translated_keywords = []
        for kw in keywords:
            # 한글이 포함되어 있는지 확인
            has_korean = any(ord('가') <= ord(char) <= ord('힣') for char in kw)
            
            if has_korean and self.pexels_downloader and hasattr(self.pexels_downloader, 'translate_to_english'):
                # 번역 시도
                try:
                    eng_keyword = self.pexels_downloader.translate_to_english(kw)
                    if eng_keyword and eng_keyword != kw:
                        print(f"🌐 '{kw}'를 영어로 번역: '{eng_keyword}'")
                        translated_keywords.append(eng_keyword)
                        # 원본 키워드도 유지
                        translated_keywords.append(kw)
                    else:
                        translated_keywords.append(kw)
                except Exception as e:
                    print(f"⚠️ 번역 오류: {str(e)}")
                    translated_keywords.append(kw)
            else:
                translated_keywords.append(kw)
        
        # 번역된 키워드가 있다면 원래 키워드 목록을 확장
        if translated_keywords and translated_keywords != keywords:
            keywords = list(dict.fromkeys(translated_keywords))  # 중복 제거하며 순서 유지
            print(f"🔄 최종 검색 키워드 목록(번역 포함): {keywords}")
        
        # 각 키워드에 대해 순차적으로 검색
        for kw in keywords:
            print(f"🔍 '{kw}' 키워드로 검색 시도 중...")
            results = self.search_music(kw, limit, use_cache)
            
            # 결과가 있으면 반환
            if results:
                print(f"✅ '{kw}' 키워드로 {len(results)}개 결과 발견")
                return results
                
        # 모든 키워드로 검색해도 결과가 없으면 빈 리스트 반환
        print("⚠️ 모든 키워드로 검색했으나 결과 없음")
        return []
    
    def get_music(self, keyword: str = None, min_duration: float = 10) -> Optional[str]:
        """
        키워드 기반으로 음악 검색 및 다운로드
        
        Args:
            keyword: 검색 키워드 (없으면 기본 카테고리 사용)
            min_duration: 최소 음악 길이 (초)
            
        Returns:
            Optional[str]: 다운로드된 음악 파일 경로
        """
        # 키워드 기본값 설정
        if not keyword:
            keyword = "calm"
            
        # 오프라인 모드 확인
        if self.offline_mode:
            self._update_progress(f"오프라인 모드: 저장된 음악 파일 사용", 10)
            return self._get_offline_music(keyword, min_duration)
        
        # 캐시 확인
        if "downloads" in self.cache:
            # 일치하는 키워드 및 길이 조건으로 파일 필터링
            matching_tracks = []
            for track_id, track_info in self.cache["downloads"].items():
                # 파일 경로 및 메타데이터 가져오기
                filepath = track_info.get("filepath")
                track_duration = track_info.get("duration", 0)
                track_tags = track_info.get("tags", "").lower()
                track_name = track_info.get("name", "").lower()
                
                # 키워드 포함 및 길이 조건 확인
                if filepath and os.path.exists(filepath) and track_duration >= min_duration:
                    # 키워드 관련성 체크
                    if (keyword.lower() in track_tags or 
                        keyword.lower() in track_name or
                        "ambient" in track_tags or
                        "calm" in track_tags or
                        "background" in track_tags):
                        matching_tracks.append((filepath, track_duration))
            
            # 일치하는 파일이 있으면 랜덤 선택
            if matching_tracks:
                # 더 긴 트랙에 약간의 가중치 부여하지만 완전 랜덤은 아님
                self._update_progress(f"'{keyword}' 관련 캐시된 음악 {len(matching_tracks)}개 발견", 15)
                filepath, duration = random.choice(matching_tracks)
                self._update_progress(f"'{os.path.basename(filepath)}' 선택 ({duration:.1f}초)", 100)
                return filepath
                
        # 콤마로 구분된 키워드 개별 검색으로 변경
        self._update_progress(f"'{keyword}' 관련 Jamendo 음악 검색 중...", 20)
        results = self.search_with_fallback(keyword)
        
        # 검색 결과 없으면 기본 키워드로 재시도
        if not results:
            self._update_progress(f"'{keyword}'에 대한 결과 없음, 기본 키워드로 재시도...", 30)
            if keyword != "calm":
                results = self.search_music("calm")
            # 그래도 없으면 로컬 파일 사용
            if not results:
                self._update_progress("검색 결과 없음, 로컬 음악 파일 사용", 35)
                return self._get_offline_music(None, min_duration)
        
        # 적합한 길이의 트랙 필터링
        suitable_tracks = [
            track for track in results
            if track.get("duration", 0) >= min_duration
        ]
        
        # 적합한 트랙이 없으면 기본 음악 사용
        if not suitable_tracks:
            self._update_progress(f"적합한 길이의 트랙 없음, 로컬 음악 파일 사용", 40)
            return self._get_offline_music(None, min_duration)
        
        # 랜덤하게 트랙 선택
        selected_track = random.choice(suitable_tracks)
        
        # 다운로드
        self._update_progress(f"'{selected_track.get('name', 'Unknown')}' 다운로드 중...", 50)
        downloaded_path = self.download_track(selected_track)
        
        if downloaded_path:
            self._update_progress(f"다운로드 완료: {os.path.basename(downloaded_path)}", 100)
            return downloaded_path
        else:
            self._update_progress(f"다운로드 실패, 로컬 음악 파일 사용", 60)
            return self._get_offline_music(None, min_duration)
            
    def _get_offline_music(self, keyword=None, min_duration=0) -> Optional[str]:
        """
        로컬 디렉토리에서 음악 파일 선택
        
        Args:
            keyword: 검색 키워드 (파일명 필터링용)
            min_duration: 최소 음악 길이 (초)
            
        Returns:
            Optional[str]: 선택된 음악 파일 경로
        """
        # 출력 디렉토리의 모든 MP3/WAV 파일 수집
        music_files = []
        for filename in os.listdir(self.output_dir):
            if filename.lower().endswith(('.mp3', '.wav', '.m4a')):
                filepath = os.path.join(self.output_dir, filename)
                
                # 키워드 일치 확인 (제공된 경우)
                if keyword and keyword.lower() not in filename.lower():
                    # 키워드가 있고 파일명에 없으면 건너뜀
                    continue
                    
                # 파일 크기 확인 (최소 10KB)
                if os.path.getsize(filepath) < 10 * 1024:
                    continue
                    
                music_files.append(filepath)
        
        # 파일이 없으면 None 반환
        if not music_files:
            self._update_progress("사용 가능한 음악 파일 없음", 100)
            return None
            
        # 랜덤 선택
        selected_file = random.choice(music_files)
        self._update_progress(f"로컬 음악 파일 선택: {os.path.basename(selected_file)}", 100)
        return selected_file


# 테스트용 코드
if __name__ == "__main__":
    # 인스턴스 생성
    jamendo = JamendoMusicProvider(output_dir="background_music")
    
    # 키워드로 음악 가져오기
    keyword = input("영상 주제 키워드를 입력하세요: ")
    if not keyword:
        keyword = "경제 뉴스"
    
    # 오디오 길이 지정 (초 단위)
    duration = 60
    
    music_path = jamendo.get_music(keyword, duration)
    
    if music_path:
        print(f"✅ 선택된 배경 음악: {music_path}")
    else:
        print("❌ 배경 음악을 찾을 수 없습니다.") 