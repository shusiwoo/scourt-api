"""
대법원 파산재산공고 스크래퍼 API
Vercel Serverless Function
"""

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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


@app.get("/")
async def root():
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
    """
    파산재산공고 목록 조회
    
    - **page**: 페이지 번호 (1부터 시작)
    - **limit**: 페이지당 항목 수 (최대 50)
    """
    notices = scraper.get_notice_list(page=page, limit=limit)
    
    # 법원별 통계
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
    """
    파산재산공고 상세 정보 조회
    
    - **detail_id**: 공고 ID (seq_id)
    """
    detail = scraper.get_notice_detail(detail_id)
    
    if not detail:
        raise HTTPException(status_code=404, detail="공고를 찾을 수 없습니다")
    
    return {
        "success": True,
        "notice": detail
    }


@app.get("/api/stats")
async def get_stats(pages: int = Query(3, ge=1, le=10, description="수집할 페이지 수")):
    """
    통계 정보 조회
    
    - **pages**: 수집할 페이지 수 (최대 10)
    """
    all_notices = []
    
    for page in range(1, pages + 1):
        notices = scraper.get_notice_list(page=page, limit=10)
        if notices:
            all_notices.extend(notices)
    
    # 법원별 통계
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
    """
    공고 검색
    
    - **keyword**: 검색어 (제목, 법원, 채무자에서 검색)
    - **pages**: 검색할 페이지 수
    """
    all_notices = []
    
    for page in range(1, pages + 1):
        notices = scraper.get_notice_list(page=page, limit=10)
        if notices:
            all_notices.extend(notices)
    
    # 키워드 필터링
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
