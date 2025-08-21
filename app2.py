import streamlit as st
import requests
import json
import base64
from PIL import Image
import io
import time
import os
import fitz  # PyMuPDF


def load_api_key():
    try:
        with open('api_key.txt', 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        st.error("api_key.txt 파일을 찾을 수 없습니다. API 키를 파일에 저장해주세요.")
        return None


class PPTStyleAnalyzer:
    def __init__(self, openai_key):
        self.openai_key = openai_key
        self.openai_url = "https://api.openai.com/v1/chat/completions"

    def analyze_pdf_with_gpt4v(self, pdf_file):
        """PDF를 페이지별 이미지로 변환 후 분석"""
        try:
            pdf_bytes = pdf_file.read()
            pdf_file.seek(0)  
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            all_styles = []

            st.info(f"PDF에서 총 {doc.page_count}페이지를 발견했습니다.")

            max_pages = min(10, doc.page_count)

            for page_num in range(max_pages):
                st.write(f"페이지 {page_num + 1} 분석 중...")

                page = doc[page_num]

                mat = fitz.Matrix(2.0, 2.0)
                pix = page.get_pixmap(matrix=mat)

                img_data = pix.tobytes("png")

                st.write(f"페이지 {page_num + 1} 이미지 크기: {len(img_data)} bytes")

                base64_image = base64.b64encode(img_data).decode()

                page_style = self.analyze_page_image(base64_image, page_num + 1)

                if page_style:
                    all_styles.append(page_style)
                    st.success(f"페이지 {page_num + 1} 분석 완료")
                else:
                    st.warning(f"페이지 {page_num + 1} 분석 실패")

            doc.close()

            if not all_styles:
                st.error("PDF에서 분석 가능한 스타일을 찾을 수 없습니다.")
                return None

            unified_style = self.merge_styles(all_styles)
            st.success(f"총 {len(all_styles)}개 페이지의 스타일을 통합했습니다.")
            return unified_style

        except Exception as e:
            st.error(f"PDF 처리 오류: {str(e)}")
            import traceback
            st.error(f"상세 오류: {traceback.format_exc()}")
            return None

    def analyze_page_image(self, base64_image, page_num):
        """개별 페이지 이미지 분석"""
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {self.openai_key}"
        }

        payload = {
            "model": "gpt-4o",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"""Analyze page {page_num} of this presentation slide and extract design patterns from diagrams, charts, and visual elements.

Look for:
- Color schemes used in diagrams/charts
- Typography styles
- Layout patterns
- Visual design elements

Return style information in the following JSON format only:

{{
  "color_palette": {{
    "primary": "#color_code",
    "secondary": "#color_code",
    "accent": "#color_code", 
    "background": "#color_code",
    "text": "#color_code"
  }},
  "typography": {{
    "title_font": "estimated_font_name",
    "body_font": "estimated_font_name",
    "title_size": "large/medium/small",
    "body_size": "large/medium/small"
  }},
  "layout": {{
    "alignment": "center/left/right",
    "spacing": "tight/normal/loose",
    "title_position": "top-center/top-left"
  }},
  "visual_style": {{
    "design_approach": "minimalist/corporate/academic",
    "border_style": "none/thin/thick",
    "shadow_style": "none/subtle/prominent"
  }},
  "brand_description": "Overall style description in one sentence",
  "has_diagrams": true/false
}}

Respond with ONLY the JSON, no other text."""
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 1000
        }

        try:
            response = requests.post(self.openai_url, headers=headers, json=payload)

            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']

                content = content.replace('```json', '').replace('```', '').strip()

                try:
                    style_data = json.loads(content)
                    return style_data
                except json.JSONDecodeError as e:
                    st.warning(f"페이지 {page_num} JSON 파싱 오류: {content[:200]}...")
                    return None
            else:
                st.warning(f"페이지 {page_num} 분석 실패: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            st.warning(f"페이지 {page_num} 분석 오류: {str(e)}")
            return None

    def merge_styles(self, styles_list):
        """여러 페이지의 스타일을 통합"""
        if not styles_list:
            return None

        if len(styles_list) == 1:
            return styles_list[0]

        merged_style = {
            "color_palette": {},
            "typography": {},
            "layout": {},
            "visual_style": {},
            "brand_description": "",
            "has_diagrams": any(style.get("has_diagrams", False) for style in styles_list)
        }

        for style in styles_list:
            if style.get("color_palette"):
                for key, value in style["color_palette"].items():
                    if key not in merged_style["color_palette"] and value:
                        merged_style["color_palette"][key] = value

        for category in ["typography", "layout", "visual_style"]:
            for style in styles_list:
                if style.get(category):
                    for key, value in style[category].items():
                        if key not in merged_style[category] and value:
                            merged_style[category][key] = value

        for style in styles_list:
            if style.get("brand_description") and not merged_style["brand_description"]:
                merged_style["brand_description"] = style["brand_description"]
                break

        return merged_style

    def analyze_ppt_style_single_image(self, image_data):
        """단일 이미지 분석 (기존 방법)"""
        if isinstance(image_data, bytes):
            base64_image = base64.b64encode(image_data).decode()
        else:
            base64_image = base64.b64encode(image_data.read()).decode()
            image_data.seek(0)

        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {self.openai_key}"
        }

        payload = {
            "model": "gpt-4o",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": """Analyze this presentation slide and extract design patterns from diagrams, charts, and visual elements.

Return style information in the following JSON format only:

{
  "color_palette": {
    "primary": "#color_code",
    "secondary": "#color_code", 
    "accent": "#color_code",
    "background": "#color_code",
    "text": "#color_code"
  },
  "typography": {
    "title_font": "estimated_font_name",
    "body_font": "estimated_font_name",
    "title_size": "large/medium/small",
    "body_size": "large/medium/small"
  },
  "layout": {
    "alignment": "center/left/right", 
    "spacing": "tight/normal/loose",
    "title_position": "top-center/top-left"
  },
  "visual_style": {
    "design_approach": "minimalist/corporate/academic",
    "border_style": "none/thin/thick",
    "shadow_style": "none/subtle/prominent"
  },
  "brand_description": "Overall style description in one sentence"
}

Respond with ONLY the JSON, no other text."""
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 1000
        }

        try:
            response = requests.post(self.openai_url, headers=headers, json=payload)

            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']
                content = content.replace('```json', '').replace('```', '').strip()
                style_data = json.loads(content)
                return style_data
            else:
                st.error(f"스타일 분석 실패: {response.status_code}")
                return None
        except Exception as e:
            st.error(f"스타일 분석 오류: {str(e)}")
            return None


class NaturalLanguageProcessor:
    def __init__(self, openai_key):
        self.openai_key = openai_key
        self.openai_url = "https://api.openai.com/v1/chat/completions"

    def process_user_request(self, user_input):
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {self.openai_key}"
        }

        payload = {
            "model": "gpt-4o",
            "messages": [
                {
                    "role": "user",
                    "content": f"""Analyze the following natural language request and convert it to PPT content requirements:

"{user_input}"

Respond in the following JSON format only:
{{
  "content_type": "graph/chart/diagram/table/text",
  "main_topic": "main subject",
  "specific_elements": ["specific element1", "specific element2"],
  "data_structure": "required data structure description",
  "visual_requirements": "visual requirements",
  "educational_goal": "educational purpose"
}}

Respond with ONLY the JSON, no other text."""
                }
            ],
            "max_tokens": 800
        }

        try:
            response = requests.post(self.openai_url, headers=headers, json=payload)

            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']
                content = content.replace('```json', '').replace('```', '').strip()
                content_data = json.loads(content)
                return content_data
            else:
                st.error(f"자연어 처리 실패: {response.status_code}")
                return None
        except Exception as e:
            st.error(f"자연어 처리 오류: {str(e)}")
            return None


class SVGGenerator:
    def __init__(self, openai_key):
        self.openai_key = openai_key
        self.openai_url = "https://api.openai.com/v1/chat/completions"

    def generate_svg(self, style_data, content_data):
        prompt = self.create_svg_prompt(style_data, content_data)

        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {self.openai_key}"
        }

        payload = {
            "model": "gpt-4o",
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": 4000
        }

        try:
            response = requests.post(self.openai_url, headers=headers, json=payload)

            if response.status_code == 200:
                result = response.json()
                svg_content = result['choices'][0]['message']['content']

                svg_start = svg_content.find('<svg')
                svg_end = svg_content.find('</svg>') + 6

                if svg_start != -1 and svg_end != -1:
                    clean_svg = svg_content[svg_start:svg_end]
                    return clean_svg, prompt
                else:
                    st.error("SVG 형식을 찾을 수 없습니다")
                    return None, None
            else:
                st.error(f"SVG 생성 실패: {response.status_code}")
                return None, None
        except Exception as e:
            st.error(f"SVG 생성 오류: {str(e)}")
            return None, None

    def create_svg_prompt(self, style_data, content_data):
        if not style_data or not content_data:
            return "Create a simple SVG diagram for a presentation slide"

        colors = style_data.get('color_palette', {})
        primary_color = colors.get('primary', '#1f4e79')
        secondary_color = colors.get('secondary', '#5b9bd5')
        accent_color = colors.get('accent', '#f79646')
        background_color = colors.get('background', '#ffffff')
        text_color = colors.get('text', '#2f2f2f')

        typography = style_data.get('typography', {})
        title_font = typography.get('title_font', 'Arial Bold')
        body_font = typography.get('body_font', 'Arial Regular')

        layout = style_data.get('layout', {})
        alignment = layout.get('alignment', 'center')
        title_position = layout.get('title_position', 'top-center')

        visual_style = style_data.get('visual_style', {})
        design_approach = visual_style.get('design_approach', 'professional')

        content_type = content_data.get('content_type', 'diagram')
        main_topic = content_data.get('main_topic', 'Technical diagram')
        specific_elements = content_data.get('specific_elements', [])

        prompt = f"""
Generate a clean, professional SVG diagram for a presentation slide matching this exact style:

CONTENT REQUIREMENTS:
- Type: {content_type}
- Topic: {main_topic}
- Elements needed: {', '.join(specific_elements)}

STYLE SPECIFICATIONS:
- Colors: Primary {primary_color}, Secondary {secondary_color}, Accent {accent_color}
- Background: {background_color}
- Text color: {text_color}
- Fonts: Title "{title_font}", Body "{body_font}"
- Layout: {alignment} aligned, title {title_position}
- Design approach: {design_approach}

SVG REQUIREMENTS:
- Create a complete SVG (width="1024" height="768")
- Clean, simple shapes - circles, rectangles, lines only
- Professional presentation quality
- Readable text with appropriate font sizes
- Proper spacing and margins
- Use exact color codes specified above
- Include title and clear labels
- Simple, educational diagram style (NOT artistic or 3D)

IMPORTANT: Respond with ONLY the complete SVG code, starting with <svg> and ending with </svg>. Do not include any explanation or markdown formatting.

Example structure for neural network:
- Use circles for nodes
- Use straight lines for connections  
- Label each layer clearly
- Keep it flat and 2D
- Use grid-like positioning
"""

        return prompt


class PPTGenerationPipeline:
    def __init__(self, openai_key):
        self.style_analyzer = PPTStyleAnalyzer(openai_key)
        self.nlp_processor = NaturalLanguageProcessor(openai_key)
        self.svg_generator = SVGGenerator(openai_key)

    def generate_ppt_slide(self, uploaded_file, user_request):
        # 1. 스타일 분석
        with st.status("PPT 스타일 분석 중...", expanded=True) as status:
            style_data = self.style_analyzer.analyze_pdf_with_gpt4v(uploaded_file)

            if not style_data:
                status.update(label="스타일 분석 실패", state="error")
                return None

            status.update(label="스타일 분석 완료", state="complete")

        # 2. 자연어 처리
        with st.status("자연어 요청 처리 중...", expanded=False) as status:
            content_data = self.nlp_processor.process_user_request(user_request)

            if not content_data:
                status.update(label="자연어 처리 실패", state="error")
                return None

            status.update(label="자연어 처리 완료", state="complete")

        # 3. SVG 생성
        with st.status("SVG 다이어그램 생성 중...", expanded=False) as status:
            svg_content, final_prompt = self.svg_generator.generate_svg(style_data, content_data)

            if not svg_content:
                status.update(label="SVG 생성 실패", state="error")
                return None

            status.update(label="SVG 생성 완료", state="complete")

        return {
            "svg_content": svg_content,
            "extracted_style": style_data,
            "processed_content": content_data,
            "final_prompt": final_prompt
        }


def load_background_image():
    """배경 이미지 로드"""
    background_path = "background.png" 
    if os.path.exists(background_path):
        return background_path
    return None


def set_background_style():
    """배경 스타일 설정"""
    background_path = load_background_image()

    if background_path:
        st.markdown(f"""
        <style>
        .stApp {{
            background: linear-gradient(rgba(255,255,255,0.8), rgba(255,255,255,0.8)), url('data:image/jpeg;base64,{get_base64_image(background_path)}');
            background-size: 729px 956px;
            background-position: center;
            background-repeat: no-repeat;
            background-attachment: fixed;
        }}

        .main-container {{
            background-color: rgba(255, 255, 255, 0.95);
            padding: 2rem;
            border-radius: 15px;
            margin: 2rem auto;
            max-width: 800px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
        }}

        .upload-container {{
            background: white;
            padding: 2rem;
            border-radius: 12px;
            border: 2px dashed #cccccc;
            margin-bottom: 2rem;
            text-align: center;
        }}

        .input-container {{
            background: white;
            padding: 2rem;
            border-radius: 12px;
            border: 1px solid #e0e0e0;
            margin-bottom: 2rem;
        }}

        .result-container {{
            background: white;
            padding: 2rem;
            border-radius: 12px;
            border: 1px solid #e0e0e0;
            margin-top: 2rem;
        }}

        .title {{
            text-align: center;
            font-size: 2.5rem;
            font-weight: 600;
            color: #2c3e50;
            margin-bottom: 0.5rem;
        }}

        .subtitle {{
            text-align: center;
            font-size: 1.2rem;
            color: #7f8c8d;
            margin-bottom: 2rem;
        }}
        </style>
        """, unsafe_allow_html=True)
    else:
        # 배경 이미지가 없는 경우 - 그라데이션 배경
        st.markdown("""
        <style>
        .stApp {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }

        .main-container {
            background-color: rgba(255, 255, 255, 0.95);
            padding: 2rem;
            border-radius: 15px;
            margin: 2rem auto;
            max-width: 800px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
        }

        .upload-container {
            background: white;
            padding: 2rem;
            border-radius: 12px;
            border: 2px dashed #cccccc;
            margin-bottom: 2rem;
            text-align: center;
        }

        .input-container {
            background: white;
            padding: 2rem;
            border-radius: 12px;
            border: 1px solid #e0e0e0;
            margin-bottom: 2rem;
        }

        .result-container {
            background: white;
            padding: 2rem;
            border-radius: 12px;
            border: 1px solid #e0e0e0;
            margin-top: 2rem;
        }

        .title {
            text-align: center;
            font-size: 2.5rem;
            font-weight: 600;
            color: #2c3e50;
            margin-bottom: 0.5rem;
        }

        .subtitle {
            text-align: center;
            font-size: 1.2rem;
            color: #7f8c8d;
            margin-bottom: 2rem;
        }
        </style>
        """, unsafe_allow_html=True)


def get_base64_image(image_path):
    """이미지를 base64로 변환"""
    try:
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode()
    except:
        return ""


def main():
    st.set_page_config(
        page_title="PPT Style Generator",
        page_icon="🎨",
        layout="wide",
        initial_sidebar_state="collapsed"
    )

    set_background_style()

    openai_key = load_api_key()
    if not openai_key:
        return

    if 'pipeline' not in st.session_state:
        st.session_state.pipeline = PPTGenerationPipeline(openai_key)

    st.markdown('<div class="title">Welcome to CNU Img Generator</div>', unsafe_allow_html=True)
    st.markdown('<div class="subtitle">Upload your PPT and generate custom diagrams</div>', unsafe_allow_html=True)

    uploaded_file = st.file_uploader(
        "Choose a PDF file",
        type=['pdf'],
        help="Upload a PDF of your PPT slides to learn the style",
        label_visibility="collapsed"
    )

    if uploaded_file:
        st.success("PDF 파일이 업로드되었습니다!")

    st.markdown('</div>', unsafe_allow_html=True)

    user_input = st.text_area(
        "Enter your request in natural language:",
        height=100,
        placeholder="Example: Create a 4-layer neural network diagram with input, hidden, and output layers",
        label_visibility="collapsed"
    )

    st.markdown('</div>', unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        generate_button = st.button(
            "Generate Diagram",
            type="primary",
            use_container_width=True,
            disabled=not (uploaded_file and user_input)
        )

    if generate_button and uploaded_file and user_input:
        st.markdown('<div class="result-container">', unsafe_allow_html=True)

        result = st.session_state.pipeline.generate_ppt_slide(uploaded_file, user_input)

        if result:
            st.markdown("### Generated Diagram")

            st.components.v1.html(
                f"""
                <div style="display: flex; justify-content: center; background: white; padding: 20px; border-radius: 10px; border: 1px solid #e0e0e0;">
                    {result["svg_content"]}
                </div>
                """,
                height=800
            )

            col1, col2 = st.columns(2)

            with col1:
                st.download_button(
                    label="Download SVG",
                    data=result["svg_content"],
                    file_name="generated_diagram.svg",
                    mime="image/svg+xml",
                    use_container_width=True
                )

            with col2:
                try:
                    import cairosvg
                    png_data = cairosvg.svg2png(bytestring=result["svg_content"].encode('utf-8'))
                    st.download_button(
                        label="Download PNG",
                        data=png_data,
                        file_name="generated_diagram.png",
                        mime="image/png",
                        use_container_width=True
                    )
                except ImportError:
                    st.info("Install cairosvg for PNG export: pip install cairosvg")

            with st.expander("View Analysis Details"):
                col1, col2 = st.columns(2)

                with col1:
                    st.markdown("**Extracted Style:**")
                    st.json(result["extracted_style"])

                with col2:
                    st.markdown("**Content Analysis:**")
                    st.json(result["processed_content"])

        else:
            st.error("Failed to generate diagram. Please try again.")

        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)


if __name__ == "__main__":
    main()