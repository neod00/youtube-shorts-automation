"""
콘텐츠 추출기 모듈
외부 소스(유튜브, 웹사이트, 사용자 입력)에서 콘텐츠를 추출하고 쇼츠용 스크립트 형태로 가공
"""

import os
import re
import json
import logging
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import textwrap

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='content_extractor.log',
    filemode='a'
)
logger = logging.getLogger('content_extractor')

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    YOUTUBE_API_AVAILABLE = True
except ImportError:
    logger.warning("YouTube API를 불러올 수 없습니다. pip install youtube-transcript-api 명령어로 설치하세요.")
    YOUTUBE_API_AVAILABLE = False

try:
    import nltk
    from nltk.tokenize import sent_tokenize
    from nltk.corpus import stopwords
    NLTK_AVAILABLE = True
    try:
        # 필요한 NLTK 데이터 미리 다운로드
        nltk.data.find('punkt')
        nltk.download('punkt')
    except LookupError:
        nltk.download('punkt')
    try:
        nltk.data.find('stopwords')
    except LookupError:
        nltk.download('stopwords')
except ImportError:
    logger.warning("NLTK를 불러올 수 없습니다. pip install nltk 명령어로 설치하세요.")
    NLTK_AVAILABLE = False

# 헤더 설정 (웹사이트 크롤링용)
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

class ContentExtractor:
    """콘텐츠 추출 및 가공 클래스"""
    
    def __init__(self, progress_callback=None):
        """초기화"""
        self.progress_callback = progress_callback
        
    def update_progress(self, message, progress=None):
        """진행 상황 업데이트"""
        logger.info(f"{progress}% - {message}" if progress else message)
        print(f"{progress}% - {message}" if progress else message)
        if self.progress_callback:
            self.progress_callback(message, progress)

    def extract_from_youtube(self, youtube_url):
        """YouTube URL에서 콘텐츠 추출"""
        try:
            # YouTube 동영상 ID 추출
            video_id = self._extract_youtube_id(youtube_url)
            if not video_id:
                self.update_progress("유효한 YouTube URL이 아닙니다.")
                return "오류: 유효한 YouTube URL이 아닙니다."
            
            self.update_progress("YouTube 자막 추출 중...", 10)
            
            if not YOUTUBE_API_AVAILABLE:
                error_msg = "YouTube 트랜스크립트 API가 설치되지 않았습니다."
                self.update_progress(error_msg, 100)
                return f"오류: {error_msg}"
            
            try:
                # 트랜스크립트 가져오기 시도
                self.update_progress("자막 추출 시도 중...", 30)
                
                try:
                    # 한국어와 영어 자막 모두 시도 (예시 코드와 동일하게)
                    transcript_list = YouTubeTranscriptApi.get_transcript(
                        video_id, 
                        languages=['ko', 'en']  # 한국어 우선, 없으면 영어
                    )
                    
                    self.update_progress("자막 추출 성공", 50)
                    
                    # 트랜스크립트 텍스트 조합 (단순화)
                    transcript_text = " ".join([item['text'] for item in transcript_list])
                    
                    # 영상 정보 가져오기
                    self.update_progress("YouTube 영상 정보 가져오는 중...", 60)
                    video_info = self._get_youtube_info(video_id)
                    
                    # 스크립트 형태로 변환 (단순화)
                    self.update_progress("스크립트 생성 중...", 80)
                    
                    # 문장 단위로 분리 (NLTK 사용하지 않고 기본 정규식만 사용)
                    sentences = []
                    try:
                        # 기본 구분자로 문장 분리 (마침표, 느낌표, 물음표 뒤에 공백이 있는 경우)
                        sentences = re.split(r'(?<=[.!?])\s+', transcript_text)
                        
                        # 결과가 없거나 하나의 긴 문장만 있다면 다른 방식 시도
                        if len(sentences) <= 1 and len(transcript_text) > 100:
                            # 간단한 구분자로 분리 (마침표, 느낌표, 물음표 기준)
                            sentences = re.split(r'[.!?]+', transcript_text)
                    except Exception as sent_error:
                        logger.warning(f"문장 분리 오류: {sent_error}")
                        # 오류 발생시 원본 텍스트를 그대로 배열에 넣음
                        sentences = [transcript_text]
                    
                    # 빈 문장 제거 및 정리
                    sentences = [s.strip() for s in sentences if s.strip()]
                    
                    # 문장이 없으면 원본 텍스트 사용
                    if not sentences:
                        sentences = [transcript_text]
                    
                    # 스크립트 형식으로 구성
                    formatted_text = "\n\n".join(sentences)
                    
                    # 비디오 제목 추가
                    title = video_info.get('title', 'YouTube 비디오')
                    script = f"# {title}\n\n{formatted_text}\n"
                    
                    # 추출 성공 언어 확인 시도
                    lang_code = "en"  # 기본값
                    if transcript_list and len(transcript_list) > 0:
                        if 'language' in transcript_list[0]:
                            lang_code = transcript_list[0]['language']
                        elif 'language_code' in transcript_list[0]:
                            lang_code = transcript_list[0]['language_code']
                    
                    # 언어 표시
                    lang_display = "한국어" if lang_code == "ko" else "영어"
                    self.update_progress(f"YouTube 콘텐츠 추출 완료 (언어: {lang_display})", 100)
                    return script
                    
                except Exception as transcript_error:
                    # 오류 처리 (간소화)
                    if "No transcript found" in str(transcript_error):
                        error_msg = "이 비디오에서 자막을 찾을 수 없습니다."
                    elif "Subtitles are disabled" in str(transcript_error):
                        error_msg = "이 비디오는 자막이 비활성화되어 있습니다."
                    else:
                        error_msg = f"자막 추출 실패: {str(transcript_error)}"
                    
                    logger.error(f"YouTube 자막 추출 오류: {transcript_error}")
                    
                    # 영상 정보만이라도 가져오기
                    try:
                        video_info = self._get_youtube_info(video_id)
                        title = video_info.get('title', 'YouTube 동영상')
                        
                        # 오류 메시지를 포함한 기본 스크립트 반환
                        error_script = f"# {title}\n\n오류: {error_msg}\n다른 영상을 시도하거나 직접 스크립트를 입력해주세요."
                        
                        self.update_progress(error_msg, 100)
                        return error_script
                    except Exception:
                        self.update_progress(error_msg, 100)
                        return f"오류: {error_msg}"
                
            except Exception as e:
                # 일반적인 예외 처리
                error_msg = f"YouTube 콘텐츠 추출 중 오류 발생: {str(e)}"
                logger.error(error_msg)
                self.update_progress(error_msg, 100)
                return f"오류: {error_msg}"
                
        except Exception as e:
            error_msg = f"YouTube URL 처리 중 오류 발생: {str(e)}"
            logger.error(error_msg)
            self.update_progress(error_msg, 100)
            return f"오류: {error_msg}"
    
    def extract_from_url(self, url):
        """웹사이트 URL에서 콘텐츠 추출"""
        try:
            self.update_progress("웹페이지 내용 가져오는 중...", 10)
            
            # URL 유효성 확인
            if not self._is_valid_url(url):
                self.update_progress("유효한 URL이 아닙니다.")
                return "오류: 유효한 URL이 아닙니다."
            
            # 웹페이지 가져오기
            response = requests.get(url, headers=HEADERS, timeout=10)
            response.raise_for_status()
            
            # 인코딩 처리
            if 'charset' in response.headers.get('content-type', '').lower():
                # Content-Type 헤더에서 charset 정보 가져오기
                content_type = response.headers.get('content-type', '').lower()
                charset_match = re.search(r'charset=([^\s;]+)', content_type)
                if charset_match:
                    charset = charset_match.group(1)
                    response.encoding = charset
                else:
                    response.encoding = response.apparent_encoding
            else:
                # charset 정보가 없으면 apparent_encoding 사용
                response.encoding = response.apparent_encoding
            
            # 한글 웹사이트 처리를 위한 추가 인코딩 설정
            if 'naver.com' in url or 'daum.net' in url or '.kr' in url:
                # 한국 사이트는 대부분 UTF-8 또는 EUC-KR 사용
                if response.encoding.lower() not in ['utf-8', 'utf8', 'euc-kr']:
                    # apparent_encoding이 잘못 감지되었을 수 있으므로 UTF-8로 시도
                    response.encoding = 'utf-8'
            
            # HTML 파싱
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 타이틀 추출
            title = soup.title.string if soup.title else ""
            
            # 본문 추출 (뉴스/블로그 사이트별 최적화)
            self.update_progress("본문 추출 중...", 30)
            
            domain = urlparse(url).netloc
            content = ""
            
            # 주요 한국 뉴스/블로그 사이트별 최적화
            if 'naver.com' in domain:
                if 'blog.naver.com' in domain:
                    content = self._extract_naver_blog(soup, url)
                else:
                    content = self._extract_naver_news(soup)
            elif 'daum.net' in domain:
                content = self._extract_daum(soup)
            elif 'tistory.com' in domain:
                content = self._extract_tistory(soup)
            else:
                # 일반적인 추출 로직
                content = self._extract_general_content(soup)
            
            # 요약 및 스크립트 생성
            self.update_progress("스크립트 생성 중...", 60)
            
            if not content:
                self.update_progress("추출할 본문을 찾을 수 없습니다.")
                return "오류: 추출할 본문을 찾을 수 없습니다."
            
            # 인코딩 문제 확인 및 해결 시도
            if any('\ufffd' in c for c in content):
                # (U+FFFD) 문자가 있으면 인코딩 문제가 있는 것
                logger.warning("추출된 콘텐츠에 인코딩 문제가 발견되었습니다. 수정 시도 중...")
                try:
                    # 다양한 인코딩 시도
                    for encoding in ['utf-8', 'euc-kr', 'cp949']:
                        try:
                            # 원본 텍스트로부터 다시 인코딩 시도
                            if hasattr(response, 'content'):
                                decoded = response.content.decode(encoding, errors='ignore')
                                if '\ufffd' not in decoded:
                                    # 성공적으로 디코딩된 경우
                                    soup = BeautifulSoup(decoded, 'html.parser')
                                    # 동일한 추출 로직 다시 시도
                                    if 'naver.com' in domain:
                                        if 'blog.naver.com' in domain:
                                            content = self._extract_naver_blog(soup, url)
                                        else:
                                            content = self._extract_naver_news(soup)
                                    elif 'daum.net' in domain:
                                        content = self._extract_daum(soup)
                                    elif 'tistory.com' in domain:
                                        content = self._extract_tistory(soup)
                                    else:
                                        content = self._extract_general_content(soup)
                                    
                                    logger.info(f"인코딩 문제 해결: {encoding} 인코딩 사용")
                                    break
                        except Exception as encoding_error:
                            logger.warning(f"{encoding} 인코딩 시도 실패: {encoding_error}")
                            continue
                except Exception as e:
                    logger.error(f"인코딩 문제 해결 시도 중 오류: {e}")
            
            # 최종적으로 깨진 문자 제거
            content = re.sub(r'\ufffd', '', content)
            
            script = self._summarize_and_create_script(content, title)
            
            # 최종 스크립트에서도 깨진 문자 검사 및 제거
            if any('\ufffd' in c for c in script):
                logger.warning("최종 스크립트에 인코딩 문제가 발견되었습니다. 문제 문자 제거 중...")
                script = re.sub(r'\ufffd', '', script)
            
            self.update_progress("웹 콘텐츠 추출 완료", 100)
            # 문자열 반환하도록 수정
            return script
        except Exception as e:
            logger.error(f"웹 콘텐츠 추출 중 오류 발생: {e}")
            self.update_progress(f"오류 발생: {e}")
            return f"오류: 웹 콘텐츠 추출 중 문제가 발생했습니다. {e}"
    
    def create_from_user_input(self, user_text, topic="은퇴자 지원 프로그램"):
        """사용자 입력 텍스트로 스크립트 생성"""
        try:
            self.update_progress("사용자 입력 처리 중...", 20)
            
            if not user_text or len(user_text.strip()) < 10:
                self.update_progress("충분한 텍스트가 입력되지 않았습니다.")
                return "오류: 충분한 텍스트가 입력되지 않았습니다."
            
            # 스크립트 생성
            self.update_progress("스크립트 형식으로 변환 중...", 60)
            script = self._format_user_text_as_script(user_text)
            
            # 주요 키워드 추출 및 제목 생성
            title, subtitle = self._generate_title_from_text(user_text, topic)
            
            # 제목을 스크립트에 추가하여 문자열로 반환
            final_script = f"# {title}\n\n{script}"
            
            self.update_progress("사용자 입력 스크립트 생성 완료", 100)
            return final_script
        except Exception as e:
            logger.error(f"사용자 입력 처리 중 오류 발생: {e}")
            self.update_progress(f"오류 발생: {e}")
            return f"오류: 사용자 입력 처리 중 문제가 발생했습니다. {e}"
    
    def _extract_youtube_id(self, youtube_url):
        """YouTube URL에서 동영상 ID 추출"""
        # 정규식 패턴
        patterns = [
            r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([a-zA-Z0-9_-]{11})',
            r'youtube\.com\/embed\/([a-zA-Z0-9_-]{11})',
            r'youtube\.com\/v\/([a-zA-Z0-9_-]{11})',
            r'youtube\.com\/shorts\/([a-zA-Z0-9_-]{11})'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, youtube_url)
            if match:
                return match.group(1)
        
        return None
    
    def _get_youtube_info(self, video_id):
        """YouTube API를 통해 영상 정보 가져오기"""
        try:
            logger.info(f"YouTube 영상 정보 가져오기 시작: {video_id}")
            # YouTube API를 사용하지 않고 웹 페이지에서 정보 추출 (API 키 불필요)
            url = f"https://www.youtube.com/watch?v={video_id}"
            response = requests.get(url, headers=HEADERS, timeout=10)
            response.raise_for_status()
            
            # 응답 인코딩 설정
            if 'charset' in response.headers.get('content-type', '').lower():
                response.encoding = response.apparent_encoding
            
            html = response.text
            logger.info(f"YouTube 페이지 가져오기 성공: {url}")
            
            # 제목 추출
            title_search = re.search(r'"title":"([^"]+)"', html)
            title = title_search.group(1) if title_search else "YouTube 동영상"
            
            # 설명 추출
            desc_search = re.search(r'"description":{"simpleText":"([^"]+)"', html)
            description = desc_search.group(1) if desc_search else ""
            
            # 인코딩 이스케이프된 유니코드 문자 처리
            try:
                # JSON 이스케이프된 유니코드 문자 처리
                title = title.encode('utf-8').decode('unicode_escape')
                description = description.encode('utf-8').decode('unicode_escape')
            except Exception as encoding_error:
                logger.warning(f"유니코드 이스케이프 처리 실패: {encoding_error}")
                # 이스케이프 처리 실패 시 원래 값 유지
            
            logger.info(f"YouTube 정보 가져오기 성공 - 제목: {title}")
            
            return {
                'title': title,
                'description': description,
                'video_id': video_id
            }
        except Exception as e:
            logger.error(f"YouTube 정보 가져오기 실패: {e}", exc_info=True)
            return {'title': "YouTube 동영상", 'description': "", 'video_id': video_id}
    
    def _convert_transcript_to_script(self, transcript_data, video_info):
        """YouTube 자막을 쇼츠 스크립트로 변환"""
        try:
            # 디버그: 입력 데이터 검사
            logger.info(f"_convert_transcript_to_script 입력 데이터 타입: {type(transcript_data)}")
            if isinstance(transcript_data, list) and len(transcript_data) > 0:
                logger.info(f"첫 번째 항목 타입: {type(transcript_data[0])}")
                logger.info(f"첫 번째 항목 내용: {str(transcript_data[0])[:100]}")
            
            # 자막 텍스트 병합
            full_text = ""
            
            if isinstance(transcript_data, list):
                # 일반적인 형태: 딕셔너리 리스트 (get_transcript의 결과)
                transcript_texts = []
                for item in transcript_data:
                    try:
                        if isinstance(item, dict) and 'text' in item:
                            transcript_texts.append(item['text'])
                        elif hasattr(item, 'text'):
                            # 객체 형태인 경우
                            transcript_texts.append(item.text)
                        else:
                            # 그 외의 경우
                            text_value = str(item)
                            transcript_texts.append(text_value)
                    except Exception as item_error:
                        logger.error(f"자막 항목 처리 오류: {item_error}")
                        # 오류가 있는 항목은 건너뛰기
                        continue
                
                # 병합된 텍스트 생성
                if transcript_texts:
                    full_text = " ".join(transcript_texts)
                    logger.info(f"리스트 처리 결과: {full_text[:100]}")
                else:
                    logger.error("자막 텍스트를 추출할 수 없습니다.")
                    full_text = "자막을 추출할 수 없습니다."
            elif isinstance(transcript_data, str):
                # 이미 문자열인 경우
                full_text = transcript_data
            elif hasattr(transcript_data, 'fetch') and callable(getattr(transcript_data, 'fetch')):
                # fetch 메서드가 있는 경우 (Transcript 객체일 가능성)
                try:
                    fetched_data = transcript_data.fetch()
                    return self._convert_transcript_to_script(fetched_data, video_info)
                except Exception as fetch_error:
                    logger.error(f"transcript.fetch() 실패: {fetch_error}")
                    full_text = str(transcript_data)
            else:
                # 그 외의 경우는 문자열로 변환 시도
                try:
                    full_text = str(transcript_data)
                except Exception:
                    full_text = "자막 변환 실패"
            
            # 전처리: 빈 문자열이면 오류 메시지 설정
            if not full_text.strip():
                logger.error("자막 텍스트가 비어 있습니다.")
                full_text = "자막 내용이 비어 있습니다."
            
            # 문장 분리 및 정리
            sentences = []
            if NLTK_AVAILABLE:
                try:
                    sentences = sent_tokenize(full_text)
                except Exception as nltk_error:
                    logger.error(f"NLTK 문장 분리 오류: {nltk_error}")
                    # 기본 구분자로 대체
                    sentences = re.split(r'[.!?]+', full_text)
            else:
                # 기본 구분자로 문장 분리
                sentences = re.split(r'[.!?]+', full_text)
            
            # 빈 문장 제거 및 정리
            sentences = [s.strip() for s in sentences if s.strip()]
            
            # 문장이 없으면 오류 메시지 추가
            if not sentences:
                sentences = ["자막 내용을 문장으로 분리할 수 없습니다."]
            
            # 기본 스크립트 형식으로 구성
            formatted_text = "\n\n".join(sentences)
            
            # 비디오 제목과 설명 추가
            title = video_info.get('title', 'YouTube 비디오')
            script = f"# {title}\n\n{formatted_text}\n"
            
            return script
            
        except Exception as e:
            logger.error(f"자막 변환 중 오류 발생: {e}", exc_info=True)
            # 오류가 발생해도 기본 스크립트 반환
            title = video_info.get('title', 'YouTube 비디오')
            return f"# {title}\n\n자막 변환 중 오류 발생: {e}\n스크립트를 생성할 수 없습니다.\n"
    
    def _is_valid_url(self, url):
        """URL 유효성 검사"""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except:
            return False
    
    def _extract_naver_blog(self, soup, url=None):
        """네이버 블로그 콘텐츠 추출"""
        # iframe 내 실제 콘텐츠 찾기
        try:
            # 프레임 URL 찾기
            frame_url = soup.select_one('iframe#mainFrame')['src']
            if not frame_url.startswith('http'):
                frame_url = f"https://blog.naver.com{frame_url}"
            
            # 프레임 내용 가져오기
            frame_response = requests.get(frame_url, headers=HEADERS, timeout=10)
            
            # 인코딩 설정 (네이버 블로그는 UTF-8 사용)
            frame_response.encoding = 'utf-8'
            
            frame_soup = BeautifulSoup(frame_response.text, 'html.parser')
            
            # 블로그 본문 추출
            content_element = frame_soup.select_one('div.se-main-container')
            if not content_element:
                content_element = frame_soup.select_one('div.post-content')
            
            if content_element:
                text_content = content_element.get_text(strip=True)
                return text_content
            
            # 구 버전 네이버 블로그 본문 추출 시도
            if not content_element:
                content_element = frame_soup.select_one('#postViewArea') or frame_soup.select_one('.post-content')
                if content_element:
                    return content_element.get_text(strip=True)
                
        except Exception as e:
            logger.error(f"네이버 블로그 추출 오류: {e}")
            
            # URL이 주어진 경우 직접 접근 시도
            if url:
                try:
                    direct_response = requests.get(url, headers=HEADERS, timeout=10)
                    direct_response.encoding = 'utf-8'
                    direct_soup = BeautifulSoup(direct_response.text, 'html.parser')
                    
                    # 직접 접근에서 본문 추출 시도
                    for selector in ['div.se-main-container', 'div.post-content', '#postViewArea']:
                        element = direct_soup.select_one(selector)
                        if element:
                            return element.get_text(strip=True)
                except Exception as direct_error:
                    logger.error(f"네이버 블로그 직접 접근 오류: {direct_error}")
        
        # 기본 추출 방식 시도
        return self._extract_general_content(soup)
    
    def _extract_naver_news(self, soup):
        """네이버 뉴스 콘텐츠 추출"""
        try:
            # 뉴스 본문 추출
            content_element = soup.select_one('div#dic_area')
            if not content_element:
                content_element = soup.select_one('div.news_end')
            
            if content_element:
                text_content = content_element.get_text(strip=True)
                # 유니코드 이스케이프 문자 처리
                try:
                    text_content = text_content.encode('utf-8').decode('utf-8')
                except Exception as encoding_error:
                    logger.warning(f"네이버 뉴스 인코딩 처리 실패: {encoding_error}")
                return text_content
        except Exception as e:
            logger.error(f"네이버 뉴스 추출 오류: {e}")
        
        # 기본 추출 방식 시도
        return self._extract_general_content(soup)
    
    def _extract_daum(self, soup):
        """다음 콘텐츠 추출"""
        try:
            # 다음 뉴스/블로그 본문 추출
            content_element = soup.select_one('div#article')
            if not content_element:
                content_element = soup.select_one('div.article_view')
            
            if content_element:
                text_content = content_element.get_text(strip=True)
                # 유니코드 이스케이프 문자 처리
                try:
                    text_content = text_content.encode('utf-8').decode('utf-8')
                except Exception as encoding_error:
                    logger.warning(f"다음 콘텐츠 인코딩 처리 실패: {encoding_error}")
                return text_content
        except Exception as e:
            logger.error(f"다음 콘텐츠 추출 오류: {e}")
        
        # 기본 추출 방식 시도
        return self._extract_general_content(soup)
    
    def _extract_tistory(self, soup):
        """티스토리 콘텐츠 추출"""
        try:
            # 티스토리 본문 추출
            content_element = soup.select_one('div.entry-content')
            if not content_element:
                content_element = soup.select_one('div.article')
            
            if content_element:
                text_content = content_element.get_text(strip=True)
                # 유니코드 이스케이프 문자 처리
                try:
                    text_content = text_content.encode('utf-8').decode('utf-8')
                except Exception as encoding_error:
                    logger.warning(f"티스토리 콘텐츠 인코딩 처리 실패: {encoding_error}")
                return text_content
        except Exception as e:
            logger.error(f"티스토리 추출 오류: {e}")
        
        # 기본 추출 방식 시도
        return self._extract_general_content(soup)
    
    def _extract_general_content(self, soup):
        """일반적인 웹페이지 콘텐츠 추출"""
        # 불필요한 요소 제거
        for tag in soup(['script', 'style', 'header', 'footer', 'nav']):
            tag.decompose()
        
        # 본문으로 가능성이 높은 요소 찾기
        content = ""
        
        # 가능한 본문 요소들
        content_candidates = [
            soup.select_one('article'),
            soup.select_one('div.content'),
            soup.select_one('div.article'),
            soup.select_one('div.post'),
            soup.select_one('div.entry'),
            soup.select_one('div#content'),
            soup.select_one('div#main')
        ]
        
        # 후보 중 내용이 있는 첫 번째 요소 사용
        for candidate in content_candidates:
            if candidate and len(candidate.get_text(strip=True)) > 100:
                content = candidate.get_text(strip=True)
                break
        
        # 후보에서 찾지 못했다면, 가장 텍스트가 많은 div 찾기
        if not content:
            divs = soup.find_all('div')
            div_with_most_text = max(divs, key=lambda d: len(d.get_text(strip=True)), default=None)
            if div_with_most_text:
                content = div_with_most_text.get_text(strip=True)
        
        # 여전히 내용이 없다면, body 전체 텍스트 추출
        if not content:
            content = soup.body.get_text(strip=True) if soup.body else ""
        
        # 유니코드 이스케이프 문자 처리
        try:
            content = content.encode('utf-8').decode('utf-8')
        except Exception as encoding_error:
            logger.warning(f"일반 콘텐츠 인코딩 처리 실패: {encoding_error}")
        
        return content
    
    def _get_meta_description(self, soup):
        """메타 설명 태그에서 정보 추출"""
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if not meta_desc:
            meta_desc = soup.find('meta', attrs={'property': 'og:description'})
        
        if meta_desc and 'content' in meta_desc.attrs:
            return meta_desc['content']
        
        return ""
    
    def _summarize_and_create_script(self, content, title):
        """웹 콘텐츠를 요약하여 스크립트 생성"""
        # 길이가 충분하지 않으면 요약 불필요
        if len(content) < 300:
            script = self._format_content_as_script(content, title)
            return script
        
        # NLTK를 사용한 요약 (가능한 경우)
        if NLTK_AVAILABLE:
            try:
                # 문장 분리
                sentences = sent_tokenize(content)
                
                # 너무 많은 문장이 있다면, 요약하기
                if len(sentences) > 15:
                    # 중요 문장 선택 (단순 방법: 첫 부분, 중간, 끝 부분)
                    selected = sentences[:3] + sentences[len(sentences)//2-2:len(sentences)//2+1] + sentences[-3:]
                    summary = " ".join(selected)
                else:
                    summary = content
                
                script = self._format_content_as_script(summary, title)
                return script
            except Exception as e:
                logger.error(f"NLTK 요약 오류: {e}")
        
        # NLTK가 없거나 오류 발생 시, 간단한 방법으로 요약
        # 너무 긴 텍스트는 앞 부분만 사용
        if len(content) > 1000:
            content = content[:1000]
        
        script = self._format_content_as_script(content, title)
        return script
    
    def _format_content_as_script(self, content, title):
        """웹 콘텐츠를 쇼츠 스크립트 형식으로 변환"""
        # 불필요한 공백 제거
        content = re.sub(r'\s+', ' ', content).strip()
        
        # 문장 분리
        if NLTK_AVAILABLE:
            sentences = sent_tokenize(content)
        else:
            sentences = re.split(r'(?<=[.!?])\s+', content)
        
        # 스크립트 생성
        script_lines = []
        
        # 제목으로 시작
        script_lines.append(f"{title}\n")
        
        # 처음 최대 15개 문장 선택
        selected_sentences = sentences[:15]
        
        # 각 문장을 스크립트 라인으로 변환
        for sentence in selected_sentences:
            # 문장 다듬기
            sentence = sentence.strip()
            if not sentence:
                continue
                
            # 짧은 문장은 그대로 추가
            if len(sentence) < 30:
                script_lines.append(sentence)
            else:
                # 긴 문장은 적절히 나누기
                wrapped = textwrap.wrap(sentence, width=30)
                script_lines.extend(wrapped)
        
        # 최종 스크립트
        script = "\n".join(script_lines)
        return script
    
    def _format_user_text_as_script(self, user_text):
        """사용자 입력 텍스트를 쇼츠 스크립트 형식으로 변환"""
        # 이미 줄바꿈이 있으면 존중
        if "\n" in user_text:
            lines = user_text.split("\n")
            # 빈 줄 제거
            lines = [line.strip() for line in lines if line.strip()]
            return "\n".join(lines)
        
        # 줄바꿈이 없는 경우, 문장 단위로 나누기
        if NLTK_AVAILABLE:
            sentences = sent_tokenize(user_text)
        else:
            sentences = re.split(r'(?<=[.!?])\s+', user_text)
        
        # 스크립트 생성
        script_lines = []
        
        # 각 문장을 스크립트 라인으로 변환
        for sentence in sentences:
            # 문장 다듬기
            sentence = sentence.strip()
            if not sentence:
                continue
                
            # 짧은 문장은 그대로 추가
            if len(sentence) < 30:
                script_lines.append(sentence)
            else:
                # 긴 문장은 적절히 나누기
                wrapped = textwrap.wrap(sentence, width=30)
                script_lines.extend(wrapped)
        
        # 최종 스크립트
        script = "\n".join(script_lines)
        return script
    
    def _generate_title_from_text(self, text, topic="은퇴자 지원 프로그램"):
        """텍스트에서 제목과 부제목 생성"""
        # 기본 제목 및 부제목 설정
        default_title = f"{topic} 정보"
        default_subtitle = "알아두면 도움되는 팁"
        
        # 텍스트가 너무 짧으면 기본값 반환
        if len(text) < 50:
            return default_title, default_subtitle
        
        try:
            # NLTK 사용 가능한 경우
            if NLTK_AVAILABLE:
                # 한국어 불용어 (stopwords)
                korean_stopwords = [
                    '이', '그', '저', '것', '수', '등', '들', '및', '에서', '으로', '자', '에', '와', '한', '한다', 
                    '또한', '그리고', '따라서', '그러나', '하지만', '때문에', '위해', '있다', '없다', '통해'
                ]
                
                # 문장 분리
                sentences = sent_tokenize(text)
                
                # 첫 번째 문장을 제목으로 활용
                if sentences:
                    # 첫 문장이 너무 길면 잘라내기
                    first_sentence = sentences[0].strip()
                    if len(first_sentence) > 20:
                        # 조사 등으로 끝나는 부분 찾기
                        match = re.search(r'(.+?)(?:이다|습니다|니다|세요|해요|된다|한다|까요|군요)', first_sentence)
                        if match:
                            title = match.group(1).strip()
                        else:
                            title = first_sentence[:20] + "..."
                    else:
                        title = first_sentence
                    
                    # 부제목은 다음 문장 활용
                    if len(sentences) > 1:
                        subtitle = sentences[1].strip()
                        # 부제목이 너무 길면 잘라내기
                        if len(subtitle) > 20:
                            subtitle = subtitle[:20] + "..."
                    else:
                        subtitle = default_subtitle
                    
                    return title, subtitle
            
            # 간단한 방법: 첫 줄을 제목으로, 두 번째 줄을 부제목으로
            lines = text.split("\n")
            lines = [line.strip() for line in lines if line.strip()]
            
            if lines:
                title = lines[0]
                if len(title) > 20:
                    title = title[:20] + "..."
                
                if len(lines) > 1:
                    subtitle = lines[1]
                    if len(subtitle) > 20:
                        subtitle = subtitle[:20] + "..."
                else:
                    subtitle = default_subtitle
                
                return title, subtitle
            
        except Exception as e:
            logger.error(f"제목 생성 오류: {e}")
        
        # 오류 발생 시 기본값 반환
        return default_title, default_subtitle


# 테스트 코드
if __name__ == "__main__":
    extractor = ContentExtractor()
    
    # 유튜브 테스트
    youtube_url = "https://www.youtube.com/watch?v=example"
    result = extractor.extract_from_youtube(youtube_url)
    if result:
        print("YouTube 추출 결과:")
        # 문자열로 반환하도록 변경되었으므로 직접 출력
        print(f"추출된 스크립트 일부: {result[:100]}...")
    
    # 웹사이트 테스트
    web_url = "https://example.com"
    result = extractor.extract_from_url(web_url)
    if result:
        print("\n웹사이트 추출 결과:")
        # 문자열로 반환하도록 변경되었으므로 직접 출력
        print(f"추출된 스크립트 일부: {result[:100]}...")
    
    # 사용자 입력 테스트
    user_text = "65세 이상 노인 지원 프로그램에는 기초연금, 노인 일자리 지원, 건강보험 혜택이 있습니다. 특히 올해부터 주거급여가 확대되어 혜택을 받을 수 있습니다."
    result = extractor.create_from_user_input(user_text)
    if result:
        print("\n사용자 입력 결과:")
        # 문자열로 반환하도록 변경되었으므로 직접 출력
        print(f"추출된 스크립트 일부: {result[:100]}...") 