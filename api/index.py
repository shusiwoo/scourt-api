"""
대법원 파산재산공고 스크래퍼 API
Vercel Serverless Function
"""

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List, Dict, Any, Optional
import re
import logging
import os
from pathlib import Path

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI 앱 생성
app = FastAPI(
    title="대법원 파산재산공고 API",
    description="대법원 파산재산공고 데이터를 실시간으로 수집하는 API",
    version="1.0.0",
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
                    
                    notice = {
                        'num': num,
                        'court': court,
                        'debtor': debtor,
                        'title': title,
                        'detail_id': detail_id,
                        'views': views,
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
        """공고 상세 정보 가져오기"""
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
            
            # 내용
            content_elem = soup.find('div', {'class': 'view_cont'}) or soup.find('div', {'class': 'content'})
            content = content_elem.get_text(strip=True) if content_elem else ''
            
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
                            'stored_name': stored_filename
                        })
            
            return {
                'id': detail_id,
                'title': title,
                'content': content[:1000],
                'attachments': attachments,
                'attachment_count': len(attachments),
                'scraped_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"상세 정보 가져오기 실패: {e}")
            return None


# 스크래퍼 인스턴스
scraper = SCourtScraper()


# HTML 랜딩페이지
LANDING_HTML = """
<!DOCTYPE html>
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
        .card-hover:hover { transform: translateY(-5px); box-shadow: 0 20px 40px rgba(0,0,0,0.15); }
        .loading { display: inline-block; width: 20px; height: 20px; border: 3px solid #f3f3f3; border-top: 3px solid #3498db; border-radius: 50%; animation: spin 1s linear infinite; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        .fade-in { animation: fadeIn 0.5s ease-in; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
        .badge { font-size: 0.75rem; padding: 0.25rem 0.75rem; border-radius: 9999px; }
        .attachment-card { border-left: 4px solid #3b82f6; }
        .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); z-index: 1000; justify-content: center; align-items: center; }
        .modal.active { display: flex; }
        .modal-content { background: white; border-radius: 1rem; max-width: 800px; max-height: 90vh; overflow-y: auto; width: 90%; }
    </style>
</head>
<body class="bg-gray-50 min-h-screen">
    <!-- Header -->
    <header class="gradient-bg text-white">
        <div class="container mx-auto px-4 py-8">
            <div class="flex items-center justify-between">
                <div>
                    <div class="flex items-center gap-3 mb-2">
                        <i class="fas fa-landmark text-3xl"></i>
                        <h1 class="text-2xl md:text-3xl font-bold">대법원 파산재산공고</h1>
                    </div>
                    <p class="text-blue-200 text-sm md:text-base">실시간 파산재산 매각공고 조회 서비스</p>
                </div>
                <div class="hidden md:flex items-center gap-4">
                    <a href="/docs" target="_blank" class="bg-white/20 hover:bg-white/30 px-4 py-2 rounded-lg transition">
                        <i class="fas fa-book mr-2"></i>API 문서
                    </a>
                </div>
            </div>
            <!-- 검색 -->
            <div class="mt-6">
                <div class="flex flex-col md:flex-row gap-3">
                    <div class="flex-1 relative">
                        <input type="text" id="searchInput" placeholder="검색어를 입력하세요 (예: 부동산, 서울, 아파트...)" 
                               class="w-full px-4 py-3 pl-12 rounded-lg text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-400">
                        <i class="fas fa-search absolute left-4 top-1/2 transform -translate-y-1/2 text-gray-400"></i>
                    </div>
                    <button onclick="searchNotices()" class="bg-blue-600 hover:bg-blue-700 px-6 py-3 rounded-lg font-medium transition">
                        <i class="fas fa-search mr-2"></i>검색
                    </button>
                    <button onclick="loadNotices()" class="bg-white/20 hover:bg-white/30 px-6 py-3 rounded-lg font-medium transition">
                        <i class="fas fa-sync-alt mr-2"></i>새로고침
                    </button>
                </div>
            </div>
        </div>
    </header>

    <!-- Stats Section -->
    <section class="container mx-auto px-4 -mt-6 relative z-10">
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4" id="statsContainer">
            <div class="bg-white rounded-xl shadow-lg p-4 card-hover">
                <div class="flex items-center gap-3">
                    <div class="bg-blue-100 p-3 rounded-lg"><i class="fas fa-file-alt text-blue-600 text-xl"></i></div>
                    <div><p class="text-gray-500 text-sm">총 공고</p><p class="text-2xl font-bold text-gray-800" id="totalCount">-</p></div>
                </div>
            </div>
            <div class="bg-white rounded-xl shadow-lg p-4 card-hover">
                <div class="flex items-center gap-3">
                    <div class="bg-green-100 p-3 rounded-lg"><i class="fas fa-building text-green-600 text-xl"></i></div>
                    <div><p class="text-gray-500 text-sm">부동산</p><p class="text-2xl font-bold text-gray-800" id="realEstateCount">-</p></div>
                </div>
            </div>
            <div class="bg-white rounded-xl shadow-lg p-4 card-hover">
                <div class="flex items-center gap-3">
                    <div class="bg-purple-100 p-3 rounded-lg"><i class="fas fa-gavel text-purple-600 text-xl"></i></div>
                    <div><p class="text-gray-500 text-sm">법원 수</p><p class="text-2xl font-bold text-gray-800" id="courtCount">-</p></div>
                </div>
            </div>
            <div class="bg-white rounded-xl shadow-lg p-4 card-hover">
                <div class="flex items-center gap-3">
                    <div class="bg-orange-100 p-3 rounded-lg"><i class="fas fa-paperclip text-orange-600 text-xl"></i></div>
                    <div><p class="text-gray-500 text-sm">첨부파일</p><p class="text-2xl font-bold text-gray-800" id="attachmentCount">-</p></div>
                </div>
            </div>
        </div>
    </section>

    <!-- Main Content -->
    <main class="container mx-auto px-4 py-8">
        <!-- Court Filter -->
        <div class="mb-6">
            <div class="flex flex-wrap gap-2" id="courtFilters">
                <button onclick="filterByCourt('all')" class="court-filter active bg-blue-600 text-white px-4 py-2 rounded-full text-sm font-medium transition" data-court="all">전체</button>
            </div>
        </div>
        <!-- Notices List -->
        <div class="space-y-4" id="noticesContainer">
            <div class="text-center py-12"><div class="loading"></div><p class="text-gray-500 mt-4">공고 목록을 불러오는 중...</p></div>
        </div>
        <!-- Load More -->
        <div class="text-center mt-8" id="loadMoreContainer" style="display: none;">
            <button onclick="loadMore()" class="bg-gray-200 hover:bg-gray-300 text-gray-700 px-8 py-3 rounded-lg font-medium transition"><i class="fas fa-plus mr-2"></i>더 보기</button>
        </div>
    </main>

    <!-- Detail Modal -->
    <div class="modal" id="detailModal">
        <div class="modal-content p-6">
            <div class="flex justify-between items-start mb-4">
                <h2 class="text-xl font-bold text-gray-800" id="modalTitle">공고 상세</h2>
                <button onclick="closeModal()" class="text-gray-400 hover:text-gray-600"><i class="fas fa-times text-xl"></i></button>
            </div>
            <div id="modalContent"><div class="text-center py-8"><div class="loading"></div></div></div>
        </div>
    </div>

    <!-- Footer -->
    <footer class="bg-gray-800 text-white py-8 mt-12">
        <div class="container mx-auto px-4">
            <div class="flex flex-col md:flex-row justify-between items-center">
                <div class="mb-4 md:mb-0">
                    <p class="text-gray-400 text-sm"><i class="fas fa-info-circle mr-2"></i>본 서비스는 대법원 파산재산공고 정보를 자동 수집하여 제공합니다.</p>
                    <p class="text-gray-500 text-xs mt-1">데이터 출처: <a href="https://www.scourt.go.kr" target="_blank" class="text-blue-400 hover:underline">대법원 전자공고</a></p>
                </div>
                <div class="flex gap-4">
                    <a href="/docs" target="_blank" class="text-gray-400 hover:text-white transition"><i class="fas fa-book"></i> API 문서</a>
                    <a href="/api/stats" target="_blank" class="text-gray-400 hover:text-white transition"><i class="fas fa-chart-bar"></i> 통계</a>
                </div>
            </div>
        </div>
    </footer>

    <script>
        const API_BASE = '';
        let currentPage = 1;
        let allNotices = [];
        let currentFilter = 'all';

        async function loadNotices() {
            try {
                document.getElementById('noticesContainer').innerHTML = '<div class="text-center py-12"><div class="loading"></div><p class="text-gray-500 mt-4">공고 목록을 불러오는 중...</p></div>';
                const response = await fetch(`${API_BASE}/api/notices?page=1&limit=20`);
                const data = await response.json();
                if (data.success) {
                    allNotices = data.notices;
                    updateStats(data);
                    updateCourtFilters(data.court_stats);
                    renderNotices(allNotices);
                }
            } catch (error) {
                console.error('Error:', error);
                document.getElementById('noticesContainer').innerHTML = '<div class="text-center py-12"><i class="fas fa-exclamation-circle text-red-500 text-4xl mb-4"></i><p class="text-gray-500">데이터를 불러오는데 실패했습니다.</p><button onclick="loadNotices()" class="mt-4 text-blue-600 hover:underline">다시 시도</button></div>';
            }
        }

        async function searchNotices() {
            const keyword = document.getElementById('searchInput').value.trim();
            if (!keyword) { loadNotices(); return; }
            try {
                document.getElementById('noticesContainer').innerHTML = `<div class="text-center py-12"><div class="loading"></div><p class="text-gray-500 mt-4">'${keyword}' 검색 중...</p></div>`;
                const response = await fetch(`${API_BASE}/api/search?keyword=${encodeURIComponent(keyword)}&pages=5`);
                const data = await response.json();
                if (data.success) {
                    allNotices = data.notices;
                    document.getElementById('totalCount').textContent = data.match_count;
                    renderNotices(allNotices);
                }
            } catch (error) { console.error('Error:', error); }
        }

        function updateStats(data) {
            document.getElementById('totalCount').textContent = data.count;
            document.getElementById('courtCount').textContent = Object.keys(data.court_stats).length;
            const realEstate = data.notices.filter(n => n.title.includes('부동산') || n.title.includes('매각')).length;
            document.getElementById('realEstateCount').textContent = realEstate;
            document.getElementById('attachmentCount').textContent = '-';
        }

        function updateCourtFilters(courtStats) {
            const container = document.getElementById('courtFilters');
            let html = `<button onclick="filterByCourt('all')" class="court-filter ${currentFilter === 'all' ? 'bg-blue-600 text-white' : 'bg-gray-200 text-gray-700'} px-4 py-2 rounded-full text-sm font-medium transition hover:bg-blue-500 hover:text-white" data-court="all">전체</button>`;
            for (const [court, count] of Object.entries(courtStats)) {
                const isActive = currentFilter === court;
                html += `<button onclick="filterByCourt('${court}')" class="court-filter ${isActive ? 'bg-blue-600 text-white' : 'bg-gray-200 text-gray-700'} px-4 py-2 rounded-full text-sm font-medium transition hover:bg-blue-500 hover:text-white" data-court="${court}">${court} <span class="ml-1 opacity-75">(${count})</span></button>`;
            }
            container.innerHTML = html;
        }

        function filterByCourt(court) {
            currentFilter = court;
            document.querySelectorAll('.court-filter').forEach(btn => {
                btn.className = btn.dataset.court === court ? 'court-filter bg-blue-600 text-white px-4 py-2 rounded-full text-sm font-medium transition' : 'court-filter bg-gray-200 text-gray-700 px-4 py-2 rounded-full text-sm font-medium transition hover:bg-blue-500 hover:text-white';
            });
            renderNotices(court === 'all' ? allNotices : allNotices.filter(n => n.court === court));
        }

        function renderNotices(notices) {
            const container = document.getElementById('noticesContainer');
            if (notices.length === 0) {
                container.innerHTML = '<div class="text-center py-12"><i class="fas fa-search text-gray-300 text-5xl mb-4"></i><p class="text-gray-500">검색 결과가 없습니다.</p></div>';
                return;
            }
            let html = '';
            notices.forEach((notice, index) => {
                const courtColor = getCourtColor(notice.court);
                html += `<div class="bg-white rounded-xl shadow-md p-5 card-hover fade-in cursor-pointer" onclick="showDetail('${notice.detail_id}')" style="animation-delay: ${index * 0.05}s">
                    <div class="flex flex-col md:flex-row md:items-center justify-between gap-4">
                        <div class="flex-1">
                            <div class="flex items-center gap-2 mb-2"><span class="badge ${courtColor}">${notice.court}</span><span class="text-gray-400 text-sm">#${notice.num}</span></div>
                            <h3 class="text-lg font-semibold text-gray-800 mb-2 hover:text-blue-600 transition">${notice.title}</h3>
                            <p class="text-gray-500 text-sm"><i class="fas fa-user mr-1"></i>${notice.debtor}</p>
                        </div>
                        <div class="flex items-center gap-4 text-sm text-gray-400"><span><i class="fas fa-eye mr-1"></i>${notice.views}</span><i class="fas fa-chevron-right text-blue-400"></i></div>
                    </div>
                </div>`;
            });
            container.innerHTML = html;
            document.getElementById('loadMoreContainer').style.display = 'block';
        }

        function getCourtColor(court) {
            const colors = {'서울회생법원': 'bg-blue-100 text-blue-700', '수원회생법원': 'bg-green-100 text-green-700', '인천지방법원': 'bg-purple-100 text-purple-700', '광주지방법원': 'bg-orange-100 text-orange-700', '대전지방법원': 'bg-red-100 text-red-700', '부산지방법원': 'bg-yellow-100 text-yellow-700'};
            return colors[court] || 'bg-gray-100 text-gray-700';
        }

        async function showDetail(detailId) {
            const modal = document.getElementById('detailModal');
            const modalContent = document.getElementById('modalContent');
            modal.classList.add('active');
            modalContent.innerHTML = '<div class="text-center py-8"><div class="loading"></div><p class="text-gray-500 mt-4">상세 정보를 불러오는 중...</p></div>';
            try {
                const response = await fetch(`${API_BASE}/api/notices/${detailId}`);
                const data = await response.json();
                if (data.success) {
                    const notice = data.notice;
                    document.getElementById('modalTitle').textContent = notice.title || '공고 상세';
                    let attachmentsHtml = '';
                    if (notice.attachments && notice.attachments.length > 0) {
                        attachmentsHtml = `<div class="mt-6"><h4 class="font-semibold text-gray-700 mb-3"><i class="fas fa-paperclip mr-2"></i>첨부파일 (${notice.attachments.length}개)</h4><div class="space-y-2">${notice.attachments.map(att => `<div class="attachment-card bg-gray-50 p-3 rounded-lg flex items-center justify-between"><div class="flex items-center gap-3"><i class="fas fa-file-pdf text-red-500 text-xl"></i><div><p class="font-medium text-gray-800">${att.filename}</p><p class="text-xs text-gray-500">PDF 문서</p></div></div><span class="text-blue-600 text-sm"><i class="fas fa-external-link-alt"></i></span></div>`).join('')}</div></div>`;
                    }
                    modalContent.innerHTML = `<div class="space-y-4"><div class="bg-blue-50 p-4 rounded-lg"><p class="text-sm text-blue-800"><i class="fas fa-info-circle mr-2"></i>공고 ID: ${notice.id} | 수집일시: ${new Date(notice.scraped_at).toLocaleString('ko-KR')}</p></div>${notice.content ? `<div><h4 class="font-semibold text-gray-700 mb-2"><i class="fas fa-align-left mr-2"></i>공고 내용</h4><div class="bg-gray-50 p-4 rounded-lg text-gray-600 text-sm leading-relaxed">${notice.content || '내용 없음'}</div></div>` : ''}${attachmentsHtml}<div class="pt-4 border-t flex justify-end gap-3"><a href="https://www.scourt.go.kr/portal/notice/realestate/RealNoticeView.work?seq_id=${notice.id}" target="_blank" class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg transition"><i class="fas fa-external-link-alt mr-2"></i>원문 보기</a><button onclick="closeModal()" class="bg-gray-200 hover:bg-gray-300 text-gray-700 px-4 py-2 rounded-lg transition">닫기</button></div></div>`;
                }
            } catch (error) {
                console.error('Error:', error);
                modalContent.innerHTML = '<div class="text-center py-8"><i class="fas fa-exclamation-circle text-red-500 text-4xl mb-4"></i><p class="text-gray-500">상세 정보를 불러오는데 실패했습니다.</p></div>';
            }
        }

        function closeModal() { document.getElementById('detailModal').classList.remove('active'); }

        async function loadMore() {
            currentPage++;
            try {
                const response = await fetch(`${API_BASE}/api/notices?page=${currentPage}&limit=20`);
                const data = await response.json();
                if (data.success && data.notices.length > 0) {
                    allNotices = [...allNotices, ...data.notices];
                    renderNotices(allNotices);
                }
            } catch (error) { console.error('Error:', error); }
        }

        document.getElementById('searchInput').addEventListener('keypress', function(e) { if (e.key === 'Enter') searchNotices(); });
        document.getElementById('detailModal').addEventListener('click', function(e) { if (e.target === this) closeModal(); });
        loadNotices();
    </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def root():
    """랜딩 페이지"""
    return HTMLResponse(content=LANDING_HTML)


@app.get("/api/info")
async def api_info():
    """API 정보"""
    return {
        "service": "대법원 파산재산공고 API",
        "version": "1.0.0",
        "description": "대법원 파산재산공고 데이터를 실시간으로 수집하는 API",
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
    limit: int = Query(10, ge=1, le=50, description="페이지당 항목 수")
):
    """파산재산공고 목록 조회"""
    notices = scraper.get_notice_list(page=page, limit=limit)
    
    court_stats = {}
    for notice in notices:
        court = notice.get('court', '기타')
        court_stats[court] = court_stats.get(court, 0) + 1
    
    return {
        "success": True,
        "page": page,
        "limit": limit,
        "count": len(notices),
        "court_stats": court_stats,
        "notices": notices,
        "scraped_at": datetime.now().isoformat()
    }


@app.get("/api/notices/{detail_id}")
async def get_notice_detail(detail_id: str):
    """파산재산공고 상세 정보 조회"""
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
    for notice in all_notices:
        court = notice.get('court', '기타')
        court_stats[court] = court_stats.get(court, 0) + 1
    
    return {
        "success": True,
        "total_count": len(all_notices),
        "pages_scraped": pages,
        "court_stats": court_stats,
        "scraped_at": datetime.now().isoformat()
    }


@app.get("/api/search")
async def search_notices(
    keyword: str = Query(..., min_length=1, description="검색어"),
    pages: int = Query(3, ge=1, le=10, description="검색할 페이지 수")
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
    
    return {
        "success": True,
        "keyword": keyword,
        "total_searched": len(all_notices),
        "match_count": len(filtered),
        "notices": filtered,
        "scraped_at": datetime.now().isoformat()
    }


@app.get("/health")
async def health_check():
    """헬스체크"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}
