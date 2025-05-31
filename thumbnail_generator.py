"""
썸네일 생성기 모듈 - Streamlit 버전
콘텐츠 분석을 통해 적절한 썸네일을 생성하는 기능 제공
"""

import os
import logging
import streamlit as st
from PIL import Image, ImageDraw, ImageFont
from typing import Optional, Tuple, Dict

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('thumbnail_generator')

class ThumbnailGenerator:
    """썸네일 생성기 클래스 - Streamlit 버전"""
    
    def __init__(self, output_dir=None, progress_callback=None):
        """
        ThumbnailGenerator 초기화
        
        Args:
            output_dir: 썸네일 저장 디렉토리 경로
            progress_callback: 진행 상황 콜백 함수 (Streamlit 용)
        """
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.output_dir = output_dir or os.path.join(self.base_dir, "thumbnails")
        os.makedirs(self.output_dir, exist_ok=True)
        
        self.progress_callback = progress_callback
        self.width = 1280
        self.height = 720
        
        # 폰트 경로 설정
        self.font_paths = {
            'bold': "C:/Windows/Fonts/malgunbd.ttf",      # 말근고딕 볼드
            'regular': "C:/Windows/Fonts/malgun.ttf",     # 말근고딕
            'gothic': "C:/Windows/Fonts/HMKMRHD.TTF",     # HY중고딕
            'impact': "C:/Windows/Fonts/impact.ttf",      # Impact
            'gothic_bold': "C:/Windows/Fonts/HMKMMAG.TTF" # HY견고딕
        }
        
        # 폰트 존재 여부 확인 및 대체 폰트 설정
        for font_type, font_path in list(self.font_paths.items()):
            if not os.path.exists(font_path):
                # Windows 기본 폰트로 대체
                if os.path.exists("C:/Windows/Fonts/malgun.ttf"):
                    self.font_paths[font_type] = "C:/Windows/Fonts/malgun.ttf"
                elif os.path.exists("C:/Windows/Fonts/arial.ttf"):
                    self.font_paths[font_type] = "C:/Windows/Fonts/arial.ttf"
                else:
                    logger.warning(f"폰트 파일을 찾을 수 없습니다: {font_path}")
        
        # 기본 썸네일 스타일 추가
        self.default_style = {
            'color_scheme': ('1a1a1a', '333333'),  # 어두운 그레이 그라데이션
            'font': 'bold',
            'font_size': 120,
            'effect_strength': 3,
            'overlay': None,
            'accent_color': 'ffffff'  # 흰색 강조
        }
        
        # 다양한 주제별 디자인 스타일 템플릿
        self.style_templates = {
            # 엔터테인먼트/연예
            'celebrity': {
                'color_scheme': ('800080', 'ff69b4'),  # 보라색-핑크 그라데이션
                'font': 'gothic',
                'font_size': 130,
                'effect_strength': 4,
                'overlay': 'sparkles',
                'accent_color': 'ffff00'  # 노란색 강조
            },
            'music': {
                'color_scheme': ('4b0082', '9370db'),  # 인디고-보라 그라데이션
                'font': 'impact',
                'font_size': 135,
                'effect_strength': 4,
                'overlay': 'music_notes',
                'accent_color': 'ffffff'  # 흰색 강조
            },
            # 경제/금융 
            'stock_surge': {
                'color_scheme': ('003300', '00cc00'),  # 초록색 그라데이션
                'font': 'gothic_bold',
                'font_size': 140,
                'effect_strength': 5,
                'overlay': 'upward_arrow',
                'accent_color': 'ffffff'  # 흰색 강조
            },
            'stock_crash': {
                'color_scheme': ('660000', 'cc0000'),  # 빨간색 그라데이션
                'font': 'gothic_bold',
                'font_size': 140,
                'effect_strength': 5,
                'overlay': 'downward_arrow',
                'accent_color': 'ffffff'  # 흰색 강조
            },
            'market_analysis': {
                'color_scheme': ('000066', '0000cc'),  # 진한 파란색 그라데이션
                'font': 'bold',
                'font_size': 125,
                'effect_strength': 3,
                'overlay': 'chart_lines',
                'accent_color': '00ffff'  # 하늘색 강조
            },
            # 라이프스타일
            'lifestyle': {
                'color_scheme': ('dda0dd', 'ff69b4'),  # 연보라-분홍 그라데이션
                'font': 'regular',
                'font_size': 125,
                'effect_strength': 3,
                'overlay': 'lifestyle_icons',
                'accent_color': 'ffffff'  # 흰색 강조
            },
            # 음식/요리
            'food': {
                'color_scheme': ('8b4513', 'd2691e'),  # 갈색 그라데이션
                'font': 'bold',
                'font_size': 135,
                'effect_strength': 4,
                'overlay': 'food_decoration',
                'accent_color': 'ffffff'  # 흰색 강조
            },
            # 여행
            'travel': {
                'color_scheme': ('4169e1', '87ceeb'),  # 로얄블루-하늘색 그라데이션
                'font': 'gothic',
                'font_size': 130,
                'effect_strength': 4,
                'overlay': 'travel_icons',
                'accent_color': 'ffffff'  # 흰색 강조
            },
            # 게임
            'gaming': {
                'color_scheme': ('4b0082', '9400d3'),  # 진한 보라 그라데이션
                'font': 'impact',
                'font_size': 140,
                'effect_strength': 5,
                'overlay': 'gaming_effects',
                'accent_color': '00ff00'  # 네온 초록색 강조
            },
            # 교육/학습
            'education': {
                'color_scheme': ('1e90ff', '87cefa'),  # 밝은 파랑 그라데이션
                'font': 'regular',
                'font_size': 120,
                'effect_strength': 3,
                'overlay': 'education_icons',
                'accent_color': 'ffff00'  # 노란색 강조
            }
        }
        
        self.update_progress("썸네일 생성기 초기화 완료", 100)
    
    def update_progress(self, message, progress_value=None):
        """진행 상황 업데이트 (Streamlit 사용 시)"""
        if self.progress_callback:
            self.progress_callback(message, progress_value)
        else:
            logger.info(message)
    
    def create_default_thumbnail(self, keyword: str) -> Optional[str]:
        """
        기본 썸네일 생성
        
        Args:
            keyword: 썸네일 키워드
            
        Returns:
            생성된 썸네일 파일 경로
        """
        try:
            self.update_progress("기본 썸네일 생성 중...", 10)
            title = f"{keyword}|최신 소식"  # 기본 제목 형식
            self.default_style['name'] = 'default'
            thumbnail_path = self.create_thumbnail_image(title, keyword, self.default_style)
            
            if thumbnail_path:
                self.update_progress(f"기본 썸네일 생성 완료: {os.path.basename(thumbnail_path)}", 100)
            else:
                self.update_progress("썸네일 생성 실패", 100)
                
            return thumbnail_path
            
        except Exception as e:
            error_msg = f"기본 썸네일 생성 실패: {str(e)}"
            logger.error(error_msg)
            self.update_progress(error_msg, 100)
            return None

    def analyze_content_style(self, keyword: str, script_content: str) -> Dict:
        """
        콘텐츠 분석하여 적절한 스타일 결정
        
        Args:
            keyword: 콘텐츠 키워드
            script_content: 스크립트 내용
            
        Returns:
            선택된 스타일 데이터
        """
        self.update_progress("콘텐츠 스타일 분석 중...", 10)
        
        # 키워드 기반 스타일 선택 (단순화된 버전)
        keyword_lower = keyword.lower()
        
        # 키워드 기반 스타일 매핑
        style_mapping = {
            '주식': 'stock_surge',
            '경제': 'market_analysis',
            '음악': 'music',
            '연예': 'celebrity',
            '스타': 'celebrity',
            '여행': 'travel',
            '게임': 'gaming',
            '교육': 'education',
            '학습': 'education',
            '음식': 'food',
            '요리': 'food',
            '라이프': 'lifestyle',
            '생활': 'lifestyle'
        }
        
        # 키워드 매칭
        selected_style = None
        for key, style in style_mapping.items():
            if key in keyword_lower:
                selected_style = style
                break
        
        # 기본 스타일 사용
        if not selected_style:
            self.update_progress("키워드에 적합한 스타일을 찾지 못했습니다. 기본 스타일 사용", 50)
            style_data = self.default_style.copy()
            style_data['name'] = 'default'
        else:
            self.update_progress(f"선택된 스타일: {selected_style}", 50)
            style_data = self.style_templates[selected_style].copy()
            style_data['name'] = selected_style
        
        self.update_progress("콘텐츠 스타일 분석 완료", 100)
        return style_data

    def generate_thumbnail(self, keyword: str, script_content: str) -> Optional[str]:
        """
        썸네일 생성 메인 함수
        
        Args:
            keyword: 썸네일 키워드
            script_content: 스크립트 내용
            
        Returns:
            생성된 썸네일 파일 경로
        """
        try:
            self.update_progress(f"'{keyword}' 키워드로 썸네일 생성 중...", 10)
            
            # 콘텐츠 스타일 분석
            style_data = self.analyze_content_style(keyword, script_content)
            
            # 썸네일 제목 생성
            title = self.generate_thumbnail_title(keyword, script_content, style_data)
            
            # 썸네일 이미지 생성
            thumbnail_path = self.create_thumbnail_image(title, keyword, style_data)
            
            if thumbnail_path:
                self.update_progress(f"썸네일 생성 완료: {os.path.basename(thumbnail_path)}", 100)
            else:
                self.update_progress("썸네일 생성 실패", 100)
                
            return thumbnail_path
            
        except Exception as e:
            error_msg = f"썸네일 생성 실패: {str(e)}"
            logger.error(error_msg)
            self.update_progress(error_msg, 100)
            return None

    def generate_thumbnail_title(self, keyword: str, script_content: str, style_data: Dict) -> str:
        """
        썸네일 제목 생성
        
        Args:
            keyword: 콘텐츠 키워드
            script_content: 스크립트 내용
            style_data: 선택된 스타일 데이터
            
        Returns:
            생성된 제목
        """
        self.update_progress("썸네일 제목 생성 중...", 30)
        
        # 스타일에 따른 제목 형식
        style_name = style_data.get('name', 'default')
        
        title_formats = {
            'default': [f"{keyword}|최신 소식", f"{keyword} 알아보기", f"알고 계셨나요? {keyword}"],
            'stock_surge': [f"{keyword} 급등!", f"{keyword} 상승세 지속", f"{keyword} 투자 적기?"],
            'stock_crash': [f"{keyword} 폭락!", f"{keyword} 하락세 지속", f"{keyword} 투자 주의보"],
            'market_analysis': [f"{keyword} 분석", f"{keyword} 전망은?", f"{keyword} 향후 추이"],
            'celebrity': [f"{keyword} 화제", f"{keyword} 근황", f"{keyword} 최신 소식"],
            'music': [f"{keyword} 인기곡", f"{keyword} 신곡", f"{keyword} 추천"],
            'food': [f"{keyword} 맛집", f"{keyword} 레시피", f"{keyword} 추천"],
            'travel': [f"{keyword} 여행", f"{keyword} 명소", f"{keyword} 추천 코스"],
            'gaming': [f"{keyword} 공략", f"{keyword} 플레이", f"{keyword} 신작"],
            'education': [f"{keyword} 쉽게 배우기", f"{keyword} 핵심 정리", f"{keyword} 기초"]
        }
        
        # 스타일에 맞는 형식이 없으면 기본 형식 사용
        formats = title_formats.get(style_name, title_formats['default'])
        
        # 스크립트 내용 분석 (간소화된 버전)
        # 첫 60자 이내에서 '?'가 있는지 확인하여 질문형 콘텐츠인지 판단
        first_part = script_content[:60]
        is_question = '?' in first_part or '궁금' in script_content or '알아보' in script_content
        
        if is_question:
            # 질문형 콘텐츠면 질문 방식의 제목
            title = f"{keyword}, 어떻게 생각하세요?"
        else:
            # 일반 콘텐츠면 스타일에 맞는 형식 중 랜덤 선택
            import random
            title = random.choice(formats)
        
        self.update_progress(f"생성된 제목: {title}", 40)
        return title

    def create_thumbnail_image(self, title: str, keyword: str, style_data: Dict) -> Optional[str]:
        """
        썸네일 이미지 생성
        
        Args:
            title: 썸네일 제목
            keyword: 키워드
            style_data: 스타일 데이터
            
        Returns:
            생성된 썸네일 파일 경로
        """
        try:
            self.update_progress("썸네일 이미지 생성 중...", 50)
            
            # 스타일 데이터 가져오기
            color_scheme = style_data.get('color_scheme', ('1a1a1a', '333333'))
            font_name = style_data.get('font', 'bold')
            font_size = style_data.get('font_size', 120)
            effect_strength = style_data.get('effect_strength', 3)
            
            # 폰트 경로 가져오기
            font_path = self.font_paths.get(font_name, self.font_paths['bold'])
            
            # 새 이미지 생성 (그라데이션 배경)
            img = Image.new('RGB', (self.width, self.height), f"#{color_scheme[0]}")
            draw = ImageDraw.Draw(img)
            
            # 그라데이션 효과 (간소화된 버전)
            for y in range(self.height):
                # 세로 위치에 따른 색상 혼합 비율
                ratio = y / self.height
                r1, g1, b1 = int(color_scheme[0][0:2], 16), int(color_scheme[0][2:4], 16), int(color_scheme[0][4:6], 16)
                r2, g2, b2 = int(color_scheme[1][0:2], 16), int(color_scheme[1][2:4], 16), int(color_scheme[1][4:6], 16)
                
                r = int(r1 * (1 - ratio) + r2 * ratio)
                g = int(g1 * (1 - ratio) + g2 * ratio)
                b = int(b1 * (1 - ratio) + b2 * ratio)
                
                draw.line([(0, y), (self.width, y)], fill=(r, g, b))
            
            # 폰트 로드
            try:
                font = ImageFont.truetype(font_path, font_size)
            except Exception as e:
                logger.warning(f"폰트 로드 실패: {e}, 기본 폰트 사용")
                font = ImageFont.load_default()
            
            # 제목 위치 계산 (중앙)
            text_bbox = draw.textbbox((0, 0), title, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]
            
            x_position = (self.width - text_width) // 2
            y_position = (self.height - text_height) // 2
            
            # 그림자 효과와 함께 텍스트 그리기
            shadow_offset = effect_strength
            outline_width = effect_strength
            
            # 그림자 및 외곽선 효과 그리기
            for offset_x in range(-outline_width, outline_width + 1):
                for offset_y in range(-outline_width, outline_width + 1):
                    # 외곽선 (검은색)
                    if offset_x != 0 or offset_y != 0:
                        draw.text((x_position + offset_x, y_position + offset_y), title, font=font, fill="black")
            
            # 메인 텍스트 (흰색)
            draw.text((x_position, y_position), title, font=font, fill="white")
            
            # 저장
            timestamp = int(os.path.getmtime(__file__))
            filename = f"thumbnail_{keyword.replace(' ', '_')}_{timestamp}.jpg"
            filepath = os.path.join(self.output_dir, filename)
            
            img.save(filepath, quality=95)
            
            self.update_progress(f"썸네일 이미지 저장 완료: {filename}", 90)
            return filepath
            
        except Exception as e:
            error_msg = f"썸네일 이미지 생성 실패: {str(e)}"
            logger.error(error_msg)
            self.update_progress(error_msg, 100)
            return None 