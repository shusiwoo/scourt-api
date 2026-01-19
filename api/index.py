"""
대법원 파산재산공고 스크래퍼 API
Vercel Serverless Function
- 카테고리 분류 (부동산/동산/채권/기타)
- 첨부파일 핵심 정보 추출 (입찰기일, 최저가, 보증금)
"""

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List, Dict, Any, Optional
import re
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI 앱 생성
app = FastAPI(
    title="대법원 파산재산공고 API",
    description="대법원 파산재산공고 데이터를 실시간으로 수집하는 API",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def classify_category(title: str, content: str = "") -> str:
    """공고 카테고리 분류"""
    text = (title + " " + content).lower()
    
    # 부동산 키워드
    real_estate_keywords = ['부동산', '토지', '건물', '아파트', '주택', '오피스텔', '상가', '공장', '창고', '대지', '임야', '전', '답', '빌딩', '근린시설']
    # 동산 키워드
    movable_keywords = ['동산', '차량', '자동차', '기계', '설비', '장비', '재고', '물품', '가구', '집기', '비품', '중장비', '트럭']
    # 채권 키워드
    bond_keywords = ['채권', '매출채권', '대여금', '보증금반환', '임대차보증금', '공사대금', '물품대금', '용역대금', '예금', '적금', '보험금', '주식', '출자지분']
    # 무형자산 키워드
    intangible_keywords = ['무형자산', '특허', '상표', '영업권', '저작권', '지식재산', '라이선스']
    
    for kw in real_estate_keywords:
        if kw in text:
            return '부동산'
    
    for kw in movable_keywords:
        if kw in text:
            return '동산'
    
    for kw in bond_keywords:
        if kw in text:
            return '채권'
    
    for kw in intangible_keywords:
        if kw in text:
            return '기타'
    
    return '기타'


def extract_bid_info(content: str) -> Dict[str, Any]:
    """공고 내용에서 입찰 정보 추출"""
    info = {
        'bid_date': None,           # 입찰기일
        'bid_location': None,       # 입찰장소
        'minimum_price': None,      # 최저가/매각가
        'deposit': None,            # 보증금
        'deposit_rate': None,       # 보증금 비율
        'payment_deadline': None,   # 잔금납부기한
        'property_location': None,  # 소재지
        'area': None,               # 면적
    }
    
    if not content:
        return info
    
    # 입찰기일 추출 (다양한 패턴)
    date_patterns = [
        r'입찰기일[:\s]*(\d{4}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}일?)',
        r'입찰일[:\s]*(\d{4}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}일?)',
        r'매각기일[:\s]*(\d{4}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}일?)',
        r'(\d{4}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}일?)[^\d]*입찰',
        r'기일[:\s]*(\d{4}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}일?)',
    ]
    
    for pattern in date_patterns:
        match = re.search(pattern, content)
        if match:
            info['bid_date'] = match.group(1).strip()
            break
    
    # 입찰장소 추출
    location_patterns = [
        r'입찰장소[:\s]*([^\n,]+)',
        r'장소[:\s]*([^\n,]+법원[^\n,]*)',
    ]
    
    for pattern in location_patterns:
        match = re.search(pattern, content)
        if match:
            info['bid_location'] = match.group(1).strip()[:100]
            break
    
    # 금액 추출 (최저가, 매각가)
    price_patterns = [
        r'최저(?:입찰)?가(?:격)?[:\s]*([0-9,]+)\s*원',
        r'매각(?:예정)?가(?:격)?[:\s]*([0-9,]+)\s*원',
        r'감정가(?:격)?[:\s]*([0-9,]+)\s*원',
        r'(?:금|₩)\s*([0-9,]+)\s*원',
        r'([0-9]{1,3}(?:,[0-9]{3})+)\s*원',
    ]
    
    for pattern in price_patterns:
        match = re.search(pattern, content)
        if match:
            price_str = match.group(1).replace(',', '')
            try:
                info['minimum_price'] = int(price_str)
            except:
                pass
            break
    
    # 보증금 추출
    deposit_patterns = [
        r'보증금[:\s]*([0-9,]+)\s*원',
        r'입찰보증금[:\s]*([0-9,]+)\s*원',
        r'보증금[:\s]*최저(?:입찰)?가(?:격)?의?\s*(\d+)[%％]',
        r'보증금[:\s]*(\d+)[%％]',
    ]
    
    for pattern in deposit_patterns:
        match = re.search(pattern, content)
        if match:
            value = match.group(1).replace(',', '')
            if '%' in pattern or '％' in pattern:
                info['deposit_rate'] = f"{value}%"
            else:
                try:
                    info['deposit'] = int(value)
                except:
                    pass
            break
    
    # 소재지 추출
    location_addr_patterns = [
        r'소재지[:\s]*([^\n]+)',
        r'소재[:\s]*([^\n]+)',
        r'주소[:\s]*([^\n]+)',
        r'물건(?:의)?\s*표시[:\s]*([^\n]+)',
    ]
    
    for pattern in location_addr_patterns:
        match = re.search(pattern, content)
        if match:
            info['property_location'] = match.group(1).strip()[:200]
            break
    
    # 면적 추출
    area_patterns = [
        r'면적[:\s]*([0-9,.]+)\s*(?:㎡|m2|제곱미터|평)',
        r'([0-9,.]+)\s*(?:㎡|m2)',
        r'([0-9,.]+)\s*평',
    ]
    
    for pattern in area_patterns:
        match = re.search(pattern, content)
        if match:
            info['area'] = match.group(1).strip()
            break
    
    # 잔금납부기한 추출
    payment_patterns = [
        r'잔금[^\n]*기한[:\s]*(\d{4}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}일?)',
        r'대금[^\n]*납부[^\n]*기한[:\s]*(\d{4}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}일?)',
    ]
    
    for pattern in payment_patterns:
        match = re.search(pattern, content)
        if match:
            info['payment_deadline'] = match.group(1).strip()
            break
    
    return info


def format_price(price: int) -> str:
    """금액 포맷팅 (억/만원 단위)"""
    if price is None:
        return None
    
    if price >= 100000000:  # 1억 이상
        eok = price // 100000000
        man = (price % 100000000) // 10000
        if man > 0:
            return f"{eok}억 {man:,}만원"
        return f"{eok}억원"
    elif price >= 10000:  # 1만원 이상
        return f"{price // 10000:,}만원"
    else:
        return f"{price:,}원"


class SCourtScraper:
    """대법원 파산재산공고 스크래퍼"""
    
    def __init__(self):
        self.base_url = "https://www.scourt.go.kr"
        self.list_url = "https://www.scourt.go.kr/portal/notice/realestate/RealNoticeList.work"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'ko-KR,ko;q=0.9,en;q=0.8',
        })
    
    def get_notice_list(self, page: int = 1, limit: int = 10) -> List[Dict[str, Any]]:
        """공고 목록 가져오기"""
        try:
            params = {'currentPage': page}
            response = self.session.get(self.list_url, params=params, timeout=10)
            response.encoding = 'euc-kr'
            
            if response.status_code != 200:
                return []
            
            soup = BeautifulSoup(response.content, 'html.parser')
            notices = []
            
            table = soup.find('table', {'class': 'tableHor'}) or soup.find('table')
            if not table:
                return []
            
            tbody = table.find('tbody')
            if not tbody:
                return []
            
            rows = tbody.find_all('tr')
            
            for idx, row in enumerate(rows[:limit], 1):
                try:
                    cols = row.find_all('td')
                    if len(cols) < 5:
                        continue
                    
                    num = cols[0].get_text(strip=True)
                    court = cols[1].get_text(strip=True)
                    debtor = cols[2].get_text(strip=True)
                    
                    title_col = cols[3]
                    title_link = title_col.find('a')
                    
                    if not title_link:
                        continue
                    
                    title = title_link.get_text(strip=True)
                    href = title_link.get('href', '')
                    detail_id = None
                    
                    if href:
                        match = re.search(r'seq_id=(\d+)', href)
                        if match:
                            detail_id = match.group(1)
                    
                    views = cols[4].get_text(strip=True) if len(cols) > 4 else '0'
                    
                    # 카테고리 분류
                    category = classify_category(title)
                    
                    notice = {
                        'num': num,
                        'court': court,
                        'debtor': debtor,
                        'title': title,
                        'detail_id': detail_id,
                        'views': views,
                        'category': category,
                        'detail_url': f"{self.base_url}{href}" if href else None
                    }
                    
                    notices.append(notice)
                    
                except Exception as e:
                    logger.warning(f"행 파싱 오류: {e}")
                    continue
            
            return notices
            
        except Exception as e:
            logger.error(f"목록 가져오기 실패: {e}")
            return []
    
    def get_notice_detail(self, detail_id: str) -> Optional[Dict[str, Any]]:
        """공고 상세 정보 가져오기 (입찰정보 추출 포함)"""
        try:
            detail_url = f"{self.base_url}/portal/notice/realestate/RealNoticeView.work"
            params = {'seq_id': detail_id}
            
            response = self.session.get(detail_url, params=params, timeout=10)
            response.encoding = 'euc-kr'
            
            if response.status_code != 200:
                return None
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # 제목
            title_elem = soup.find('h3', {'class': 'tit'}) or soup.find('h2')
            title = title_elem.get_text(strip=True) if title_elem else 'Unknown'
            
            # 내용 (전체)
            content_elem = soup.find('div', {'class': 'view_cont'}) or soup.find('div', {'class': 'content'})
            full_content = content_elem.get_text(strip=True) if content_elem else ''
            
            # 카테고리 분류
            category = classify_category(title, full_content)
            
            # 입찰 정보 추출
            bid_info = extract_bid_info(full_content)
            
            # 첨부파일
            attachments = []
            all_links = soup.find_all('a', href=True)
            
            for link in all_links:
                href = link.get('href', '')
                text = link.get_text(strip=True)
                
                if 'download(' in href and text:
                    match = re.search(r"download\('([^']+)'\s*,\s*'([^']+)'\)", href)
                    if match:
                        stored_filename = match.group(1)
                        original_filename = match.group(2)
                        
                        attachments.append({
                            'filename': original_filename,
                            'stored_name': stored_filename,
                            'type': 'pdf' if original_filename.lower().endswith('.pdf') else 'other'
                        })
            
            return {
                'id': detail_id,
                'title': title,
                'category': category,
                'content': full_content[:2000],
                'bid_info': {
                    'bid_date': bid_info['bid_date'],
                    'bid_location': bid_info['bid_location'],
                    'minimum_price': bid_info['minimum_price'],
                    'minimum_price_formatted': format_price(bid_info['minimum_price']),
                    'deposit': bid_info['deposit'],
                    'deposit_formatted': format_price(bid_info['deposit']),
                    'deposit_rate': bid_info['deposit_rate'],
                    'payment_deadline': bid_info['payment_deadline'],
                    'property_location': bid_info['property_location'],
                    'area': bid_info['area'],
                },
                'attachments': attachments,
                'attachment_count': len(attachments),
                'scraped_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"상세 정보 가져오기 실패: {e}")
            return None


# 스크래퍼 인스턴스
scraper = SCourtScraper()


# HTML 랜딩페이지 (카테고리 탭 + 상세 입찰정보)
LANDING_HTML = '''<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>대법원 파산재산공고 - 실시간 조회 서비스</title>
    <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap');
        * { font-family: 'Noto Sans KR', sans-serif; }
        .gradient-bg { background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 50%, #3d7ab5 100%); }
        .card-hover { transition: all 0.3s ease; }
        .card-hover:hover { transform: translateY(-4px); box-shadow: 0 12px 24px rgba(0,0,0,0.15); }
        .loading { display: inline-block; width: 24px; height: 24px; border: 3px solid #e5e7eb; border-top-color: #3b82f6; border-radius: 50%; animation: spin 0.8s linear infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }
        .fade-in { animation: fadeIn 0.4s ease-out; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        .badge { font-size: 0.7rem; padding: 0.2rem 0.6rem; border-radius: 9999px; font-weight: 500; }
        .category-tab { transition: all 0.2s; border-bottom: 3px solid transparent; }
        .category-tab.active { border-bottom-color: #3b82f6; color: #3b82f6; font-weight: 600; }
        .category-tab:hover { color: #3b82f6; }
        .info-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.75rem; }
        @media (min-width: 768px) { .info-grid { grid-template-columns: repeat(3, 1fr); } }
        .info-item { background: #f8fafc; padding: 0.75rem; border-radius: 0.5rem; }
        .info-label { font-size: 0.75rem; color: #64748b; margin-bottom: 0.25rem; }
        .info-value { font-size: 0.95rem; font-weight: 600; color: #1e293b; }
        .modal { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.5); z-index: 50; justify-content: center; align-items: center; padding: 1rem; }
        .modal.active { display: flex; }
        .modal-content { background: white; border-radius: 1rem; max-width: 900px; width: 100%; max-height: 90vh; overflow-y: auto; }
        .price-highlight { background: linear-gradient(135deg, #fef3c7, #fde68a); padding: 1rem; border-radius: 0.75rem; border-left: 4px solid #f59e0b; }
        .category-badge-부동산 { background: #dbeafe; color: #1d4ed8; }
        .category-badge-동산 { background: #dcfce7; color: #15803d; }
        .category-badge-채권 { background: #fce7f3; color: #be185d; }
        .category-badge-기타 { background: #f3e8ff; color: #7c3aed; }
    </style>
</head>
<body class="bg-gray-50 min-h-screen">
    <!-- Header -->
    <header class="gradient-bg text-white">
        <div class="container mx-auto px-4 py-6">
            <div class="flex items-center justify-between mb-4">
                <div class="flex items-center gap-3">
                    <i class="fas fa-landmark text-2xl"></i>
                    <div>
                        <h1 class="text-xl md:text-2xl font-bold">대법원 파산재산공고</h1>
                        <p class="text-blue-200 text-xs md:text-sm">실시간 매각공고 조회 서비스</p>
                    </div>
                </div>
                <a href="/docs" target="_blank" class="hidden md:flex items-center gap-2 bg-white/20 hover:bg-white/30 px-3 py-2 rounded-lg text-sm transition">
                    <i class="fas fa-book"></i>API
                </a>
            </div>
            <!-- 검색 -->
            <div class="flex gap-2">
                <div class="flex-1 relative">
                    <input type="text" id="searchInput" placeholder="검색어 입력 (예: 서울, 아파트, 차량...)" 
                           class="w-full px-4 py-2.5 pl-10 rounded-lg text-gray-800 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400">
                    <i class="fas fa-search absolute left-3.5 top-1/2 -translate-y-1/2 text-gray-400 text-sm"></i>
                </div>
                <button onclick="searchNotices()" class="bg-blue-600 hover:bg-blue-700 px-4 py-2.5 rounded-lg text-sm font-medium transition">
                    검색
                </button>
            </div>
        </div>
    </header>

    <!-- Category Tabs -->
    <div class="bg-white border-b sticky top-0 z-40">
        <div class="container mx-auto px-4">
            <div class="flex gap-1 overflow-x-auto" id="categoryTabs">
                <button onclick="filterByCategory('all')" class="category-tab active px-4 py-3 text-sm whitespace-nowrap" data-category="all">
                    <i class="fas fa-th-large mr-1.5"></i>전체 <span class="count text-gray-400 ml-1">0</span>
                </button>
                <button onclick="filterByCategory('부동산')" class="category-tab px-4 py-3 text-sm whitespace-nowrap" data-category="부동산">
                    <i class="fas fa-building mr-1.5"></i>부동산 <span class="count text-gray-400 ml-1">0</span>
                </button>
                <button onclick="filterByCategory('동산')" class="category-tab px-4 py-3 text-sm whitespace-nowrap" data-category="동산">
                    <i class="fas fa-car mr-1.5"></i>동산 <span class="count text-gray-400 ml-1">0</span>
                </button>
                <button onclick="filterByCategory('채권')" class="category-tab px-4 py-3 text-sm whitespace-nowrap" data-category="채권">
                    <i class="fas fa-file-invoice-dollar mr-1.5"></i>채권 <span class="count text-gray-400 ml-1">0</span>
                </button>
                <button onclick="filterByCategory('기타')" class="category-tab px-4 py-3 text-sm whitespace-nowrap" data-category="기타">
                    <i class="fas fa-ellipsis-h mr-1.5"></i>기타 <span class="count text-gray-400 ml-1">0</span>
                </button>
            </div>
        </div>
    </div>

    <!-- Stats -->
    <section class="container mx-auto px-4 py-4">
        <div class="grid grid-cols-4 gap-2 md:gap-4">
            <div class="bg-white rounded-lg shadow p-3 text-center">
                <p class="text-lg md:text-2xl font-bold text-blue-600" id="totalCount">-</p>
                <p class="text-xs text-gray-500">전체</p>
            </div>
            <div class="bg-white rounded-lg shadow p-3 text-center">
                <p class="text-lg md:text-2xl font-bold text-green-600" id="realEstateCount">-</p>
                <p class="text-xs text-gray-500">부동산</p>
            </div>
            <div class="bg-white rounded-lg shadow p-3 text-center">
                <p class="text-lg md:text-2xl font-bold text-purple-600" id="movableCount">-</p>
                <p class="text-xs text-gray-500">동산</p>
            </div>
            <div class="bg-white rounded-lg shadow p-3 text-center">
                <p class="text-lg md:text-2xl font-bold text-pink-600" id="bondCount">-</p>
                <p class="text-xs text-gray-500">채권</p>
            </div>
        </div>
    </section>

    <!-- Court Filter -->
    <section class="container mx-auto px-4 pb-2">
        <div class="flex flex-wrap gap-1.5" id="courtFilters"></div>
    </section>

    <!-- Main Content -->
    <main class="container mx-auto px-4 pb-8">
        <div class="space-y-3" id="noticesContainer">
            <div class="text-center py-12"><div class="loading"></div><p class="text-gray-500 mt-3 text-sm">공고 목록을 불러오는 중...</p></div>
        </div>
        <div class="text-center mt-6" id="loadMoreContainer" style="display:none;">
            <button onclick="loadMore()" class="bg-gray-100 hover:bg-gray-200 text-gray-700 px-6 py-2.5 rounded-lg text-sm font-medium transition">
                <i class="fas fa-plus mr-2"></i>더 보기
            </button>
        </div>
    </main>

    <!-- Detail Modal -->
    <div class="modal" id="detailModal">
        <div class="modal-content">
            <div class="sticky top-0 bg-white border-b px-5 py-4 flex justify-between items-center">
                <h2 class="text-lg font-bold text-gray-800 truncate pr-4" id="modalTitle">공고 상세</h2>
                <button onclick="closeModal()" class="text-gray-400 hover:text-gray-600 p-1"><i class="fas fa-times text-xl"></i></button>
            </div>
            <div class="p-5" id="modalContent"><div class="text-center py-8"><div class="loading"></div></div></div>
        </div>
    </div>

    <!-- Footer -->
    <footer class="bg-gray-800 text-gray-400 py-6">
        <div class="container mx-auto px-4 text-center text-xs">
            <p>데이터 출처: <a href="https://www.scourt.go.kr" target="_blank" class="text-blue-400 hover:underline">대법원 전자공고</a></p>
            <p class="mt-1">본 서비스는 공공 정보를 자동 수집하여 제공합니다.</p>
        </div>
    </footer>

    <script>
        const API_BASE = '';
        let currentPage = 1;
        let allNotices = [];
        let currentCategory = 'all';
        let currentCourt = 'all';

        async function loadNotices() {
            try {
                showLoading();
                const response = await fetch(`${API_BASE}/api/notices?page=1&limit=30`);
                const data = await response.json();
                if (data.success) {
                    allNotices = data.notices;
                    updateStats();
                    updateCourtFilters();
                    applyFilters();
                }
            } catch (error) {
                showError();
            }
        }

        async function searchNotices() {
            const keyword = document.getElementById('searchInput').value.trim();
            if (!keyword) { loadNotices(); return; }
            try {
                showLoading(`'${keyword}' 검색 중...`);
                const response = await fetch(`${API_BASE}/api/search?keyword=${encodeURIComponent(keyword)}&pages=5`);
                const data = await response.json();
                if (data.success) {
                    allNotices = data.notices;
                    updateStats();
                    updateCourtFilters();
                    applyFilters();
                }
            } catch (error) { showError(); }
        }

        function showLoading(msg = '공고 목록을 불러오는 중...') {
            document.getElementById('noticesContainer').innerHTML = `<div class="text-center py-12"><div class="loading"></div><p class="text-gray-500 mt-3 text-sm">${msg}</p></div>`;
        }

        function showError() {
            document.getElementById('noticesContainer').innerHTML = '<div class="text-center py-12"><i class="fas fa-exclamation-circle text-red-400 text-3xl mb-3"></i><p class="text-gray-500 text-sm">데이터를 불러오는데 실패했습니다.</p><button onclick="loadNotices()" class="mt-3 text-blue-600 text-sm hover:underline">다시 시도</button></div>';
        }

        function updateStats() {
            const stats = { '부동산': 0, '동산': 0, '채권': 0, '기타': 0 };
            allNotices.forEach(n => { stats[n.category] = (stats[n.category] || 0) + 1; });
            
            document.getElementById('totalCount').textContent = allNotices.length;
            document.getElementById('realEstateCount').textContent = stats['부동산'];
            document.getElementById('movableCount').textContent = stats['동산'];
            document.getElementById('bondCount').textContent = stats['채권'];
            
            // Update tab counts
            document.querySelectorAll('.category-tab').forEach(tab => {
                const cat = tab.dataset.category;
                const countEl = tab.querySelector('.count');
                if (countEl) {
                    countEl.textContent = cat === 'all' ? allNotices.length : (stats[cat] || 0);
                }
            });
        }

        function updateCourtFilters() {
            const courts = {};
            allNotices.forEach(n => { courts[n.court] = (courts[n.court] || 0) + 1; });
            
            let html = `<button onclick="filterByCourt('all')" class="court-btn ${currentCourt === 'all' ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600'} px-3 py-1.5 rounded-full text-xs font-medium transition hover:bg-blue-500 hover:text-white" data-court="all">전체</button>`;
            
            Object.entries(courts).sort((a,b) => b[1] - a[1]).forEach(([court, count]) => {
                const isActive = currentCourt === court;
                html += `<button onclick="filterByCourt('${court}')" class="court-btn ${isActive ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600'} px-3 py-1.5 rounded-full text-xs font-medium transition hover:bg-blue-500 hover:text-white" data-court="${court}">${court} (${count})</button>`;
            });
            
            document.getElementById('courtFilters').innerHTML = html;
        }

        function filterByCategory(category) {
            currentCategory = category;
            document.querySelectorAll('.category-tab').forEach(tab => {
                tab.classList.toggle('active', tab.dataset.category === category);
            });
            applyFilters();
        }

        function filterByCourt(court) {
            currentCourt = court;
            document.querySelectorAll('.court-btn').forEach(btn => {
                const isActive = btn.dataset.court === court;
                btn.className = `court-btn ${isActive ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600'} px-3 py-1.5 rounded-full text-xs font-medium transition hover:bg-blue-500 hover:text-white`;
            });
            applyFilters();
        }

        function applyFilters() {
            let filtered = allNotices;
            if (currentCategory !== 'all') filtered = filtered.filter(n => n.category === currentCategory);
            if (currentCourt !== 'all') filtered = filtered.filter(n => n.court === currentCourt);
            renderNotices(filtered);
        }

        function renderNotices(notices) {
            const container = document.getElementById('noticesContainer');
            if (notices.length === 0) {
                container.innerHTML = '<div class="text-center py-12"><i class="fas fa-inbox text-gray-300 text-4xl mb-3"></i><p class="text-gray-500 text-sm">해당하는 공고가 없습니다.</p></div>';
                document.getElementById('loadMoreContainer').style.display = 'none';
                return;
            }
            
            container.innerHTML = notices.map((n, i) => `
                <div class="bg-white rounded-xl shadow-sm p-4 card-hover fade-in cursor-pointer border border-gray-100" onclick="showDetail('${n.detail_id}')" style="animation-delay:${i*0.03}s">
                    <div class="flex items-start gap-3">
                        <div class="flex-1 min-w-0">
                            <div class="flex flex-wrap items-center gap-1.5 mb-2">
                                <span class="badge category-badge-${n.category}">${n.category}</span>
                                <span class="badge bg-gray-100 text-gray-600">${n.court}</span>
                                <span class="text-gray-400 text-xs">#${n.num}</span>
                            </div>
                            <h3 class="font-semibold text-gray-800 text-sm md:text-base mb-1.5 line-clamp-2">${n.title}</h3>
                            <p class="text-gray-500 text-xs truncate"><i class="fas fa-user mr-1"></i>${n.debtor}</p>
                        </div>
                        <div class="flex flex-col items-end gap-1 flex-shrink-0">
                            <span class="text-gray-400 text-xs"><i class="fas fa-eye mr-1"></i>${n.views}</span>
                            <i class="fas fa-chevron-right text-blue-400 text-sm"></i>
                        </div>
                    </div>
                </div>
            `).join('');
            
            document.getElementById('loadMoreContainer').style.display = 'block';
        }

        async function showDetail(detailId) {
            const modal = document.getElementById('detailModal');
            const content = document.getElementById('modalContent');
            modal.classList.add('active');
            content.innerHTML = '<div class="text-center py-12"><div class="loading"></div><p class="text-gray-500 mt-3 text-sm">상세 정보를 불러오는 중...</p></div>';
            
            try {
                const response = await fetch(`${API_BASE}/api/notices/${detailId}`);
                const data = await response.json();
                
                if (data.success) {
                    const n = data.notice;
                    const bi = n.bid_info || {};
                    document.getElementById('modalTitle').textContent = n.title || '공고 상세';
                    
                    // 입찰정보 섹션
                    let bidInfoHtml = '';
                    if (bi.minimum_price_formatted || bi.bid_date || bi.deposit_formatted || bi.deposit_rate) {
                        bidInfoHtml = `
                            <div class="price-highlight mb-4">
                                <h4 class="font-bold text-amber-800 mb-3 flex items-center gap-2">
                                    <i class="fas fa-gavel"></i>입찰 핵심 정보
                                </h4>
                                <div class="info-grid">
                                    ${bi.minimum_price_formatted ? `<div class="info-item bg-white"><p class="info-label">최저입찰가</p><p class="info-value text-red-600">${bi.minimum_price_formatted}</p></div>` : ''}
                                    ${bi.bid_date ? `<div class="info-item bg-white"><p class="info-label">입찰기일</p><p class="info-value">${bi.bid_date}</p></div>` : ''}
                                    ${bi.deposit_formatted ? `<div class="info-item bg-white"><p class="info-label">보증금</p><p class="info-value">${bi.deposit_formatted}</p></div>` : ''}
                                    ${bi.deposit_rate ? `<div class="info-item bg-white"><p class="info-label">보증금율</p><p class="info-value">${bi.deposit_rate}</p></div>` : ''}
                                    ${bi.bid_location ? `<div class="info-item bg-white col-span-2"><p class="info-label">입찰장소</p><p class="info-value text-sm">${bi.bid_location}</p></div>` : ''}
                                    ${bi.property_location ? `<div class="info-item bg-white col-span-2 md:col-span-3"><p class="info-label">소재지</p><p class="info-value text-sm">${bi.property_location}</p></div>` : ''}
                                    ${bi.area ? `<div class="info-item bg-white"><p class="info-label">면적</p><p class="info-value">${bi.area}㎡</p></div>` : ''}
                                    ${bi.payment_deadline ? `<div class="info-item bg-white"><p class="info-label">잔금기한</p><p class="info-value">${bi.payment_deadline}</p></div>` : ''}
                                </div>
                            </div>
                        `;
                    }
                    
                    // 첨부파일 섹션
                    let attachHtml = '';
                    if (n.attachments && n.attachments.length > 0) {
                        attachHtml = `
                            <div class="mt-4">
                                <h4 class="font-semibold text-gray-700 mb-2 flex items-center gap-2"><i class="fas fa-paperclip"></i>첨부파일 (${n.attachments.length})</h4>
                                <div class="space-y-2">
                                    ${n.attachments.map(att => `
                                        <div class="flex items-center gap-3 bg-gray-50 p-3 rounded-lg border-l-4 border-blue-400">
                                            <i class="fas fa-file-pdf text-red-500"></i>
                                            <span class="flex-1 text-sm text-gray-700 truncate">${att.filename}</span>
                                        </div>
                                    `).join('')}
                                </div>
                            </div>
                        `;
                    }
                    
                    content.innerHTML = `
                        <div class="space-y-4">
                            <div class="flex items-center gap-2">
                                <span class="badge category-badge-${n.category}">${n.category}</span>
                                <span class="text-gray-400 text-xs">ID: ${n.id}</span>
                            </div>
                            
                            ${bidInfoHtml}
                            
                            ${n.content ? `
                                <div>
                                    <h4 class="font-semibold text-gray-700 mb-2 flex items-center gap-2"><i class="fas fa-file-alt"></i>공고 내용</h4>
                                    <div class="bg-gray-50 p-4 rounded-lg text-sm text-gray-600 leading-relaxed max-h-60 overflow-y-auto whitespace-pre-wrap">${n.content}</div>
                                </div>
                            ` : ''}
                            
                            ${attachHtml}
                            
                            <div class="flex gap-2 pt-4 border-t">
                                <a href="https://www.scourt.go.kr/portal/notice/realestate/RealNoticeView.work?seq_id=${n.id}" target="_blank" class="flex-1 bg-blue-600 hover:bg-blue-700 text-white text-center py-2.5 rounded-lg text-sm font-medium transition">
                                    <i class="fas fa-external-link-alt mr-2"></i>원문 보기
                                </a>
                                <button onclick="closeModal()" class="px-4 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg text-sm font-medium transition">닫기</button>
                            </div>
                        </div>
                    `;
                }
            } catch (error) {
                content.innerHTML = '<div class="text-center py-8"><i class="fas fa-exclamation-circle text-red-400 text-3xl mb-3"></i><p class="text-gray-500 text-sm">정보를 불러오는데 실패했습니다.</p></div>';
            }
        }

        function closeModal() { document.getElementById('detailModal').classList.remove('active'); }

        async function loadMore() {
            currentPage++;
            try {
                const response = await fetch(`${API_BASE}/api/notices?page=${currentPage}&limit=30`);
                const data = await response.json();
                if (data.success && data.notices.length > 0) {
                    allNotices = [...allNotices, ...data.notices];
                    updateStats();
                    updateCourtFilters();
                    applyFilters();
                }
            } catch (error) { console.error(error); }
        }

        document.getElementById('searchInput').addEventListener('keypress', e => { if (e.key === 'Enter') searchNotices(); });
        document.getElementById('detailModal').addEventListener('click', e => { if (e.target.id === 'detailModal') closeModal(); });
        loadNotices();
    </script>
</body>
</html>'''


@app.get("/", response_class=HTMLResponse)
async def root():
    """랜딩 페이지"""
    return HTMLResponse(content=LANDING_HTML)


@app.get("/api/info")
async def api_info():
    """API 정보"""
    return {
        "service": "대법원 파산재산공고 API",
        "version": "2.0.0",
        "description": "대법원 파산재산공고 데이터를 실시간으로 수집하는 API",
        "features": ["카테고리 분류 (부동산/동산/채권/기타)", "입찰정보 자동 추출", "첨부파일 분석"],
        "endpoints": {
            "공고 목록": "/api/notices",
            "공고 상세": "/api/notices/{detail_id}",
            "통계": "/api/stats",
            "API 문서": "/docs"
        },
        "source": "https://www.scourt.go.kr/portal/notice/realestate/RealNoticeList.work",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/api/notices")
async def get_notices(
    page: int = Query(1, ge=1, description="페이지 번호"),
    limit: int = Query(10, ge=1, le=50, description="페이지당 항목 수"),
    category: Optional[str] = Query(None, description="카테고리 필터 (부동산/동산/채권/기타)")
):
    """파산재산공고 목록 조회"""
    notices = scraper.get_notice_list(page=page, limit=limit)
    
    # 카테고리 필터링
    if category:
        notices = [n for n in notices if n.get('category') == category]
    
    # 통계
    court_stats = {}
    category_stats = {'부동산': 0, '동산': 0, '채권': 0, '기타': 0}
    
    for notice in notices:
        court = notice.get('court', '기타')
        court_stats[court] = court_stats.get(court, 0) + 1
        cat = notice.get('category', '기타')
        category_stats[cat] = category_stats.get(cat, 0) + 1
    
    return {
        "success": True,
        "page": page,
        "limit": limit,
        "count": len(notices),
        "court_stats": court_stats,
        "category_stats": category_stats,
        "notices": notices,
        "scraped_at": datetime.now().isoformat()
    }


@app.get("/api/notices/{detail_id}")
async def get_notice_detail(detail_id: str):
    """파산재산공고 상세 정보 조회 (입찰정보 포함)"""
    detail = scraper.get_notice_detail(detail_id)
    
    if not detail:
        raise HTTPException(status_code=404, detail="공고를 찾을 수 없습니다")
    
    return {
        "success": True,
        "notice": detail
    }


@app.get("/api/stats")
async def get_stats(pages: int = Query(3, ge=1, le=10, description="수집할 페이지 수")):
    """통계 정보 조회"""
    all_notices = []
    
    for page in range(1, pages + 1):
        notices = scraper.get_notice_list(page=page, limit=10)
        if notices:
            all_notices.extend(notices)
    
    court_stats = {}
    category_stats = {'부동산': 0, '동산': 0, '채권': 0, '기타': 0}
    
    for notice in all_notices:
        court = notice.get('court', '기타')
        court_stats[court] = court_stats.get(court, 0) + 1
        cat = notice.get('category', '기타')
        category_stats[cat] = category_stats.get(cat, 0) + 1
    
    return {
        "success": True,
        "total_count": len(all_notices),
        "pages_scraped": pages,
        "court_stats": court_stats,
        "category_stats": category_stats,
        "scraped_at": datetime.now().isoformat()
    }


@app.get("/api/search")
async def search_notices(
    keyword: str = Query(..., min_length=1, description="검색어"),
    pages: int = Query(3, ge=1, le=10, description="검색할 페이지 수"),
    category: Optional[str] = Query(None, description="카테고리 필터")
):
    """공고 검색"""
    all_notices = []
    
    for page in range(1, pages + 1):
        notices = scraper.get_notice_list(page=page, limit=10)
        if notices:
            all_notices.extend(notices)
    
    keyword_lower = keyword.lower()
    filtered = [
        n for n in all_notices
        if keyword_lower in n.get('title', '').lower()
        or keyword_lower in n.get('court', '').lower()
        or keyword_lower in n.get('debtor', '').lower()
    ]
    
    # 카테고리 필터
    if category:
        filtered = [n for n in filtered if n.get('category') == category]
    
    return {
        "success": True,
        "keyword": keyword,
        "category": category,
        "total_searched": len(all_notices),
        "match_count": len(filtered),
        "notices": filtered,
        "scraped_at": datetime.now().isoformat()
    }


@app.get("/health")
async def health_check():
    """헬스체크"""
    return {"status": "healthy", "version": "2.0.0", "timestamp": datetime.now().isoformat()}
