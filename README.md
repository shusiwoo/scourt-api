# 🏛️ 대법원 파산재산공고 API

대법원 파산재산공고 데이터를 실시간으로 수집하는 API 서비스

## 🚀 배포

### Vercel 배포

1. **Vercel CLI 설치**
```bash
npm i -g vercel
```

2. **로그인**
```bash
vercel login
```

3. **배포**
```bash
cd scourt-api
vercel
```

4. **프로덕션 배포**
```bash
vercel --prod
```

## 📡 API 엔드포인트

### 기본 정보
- `GET /` - API 정보

### 공고 목록
- `GET /api/notices` - 파산재산공고 목록 조회
  - `page`: 페이지 번호 (기본: 1)
  - `limit`: 페이지당 항목 수 (기본: 10, 최대: 50)

### 공고 상세
- `GET /api/notices/{detail_id}` - 공고 상세 정보 조회

### 검색
- `GET /api/search` - 공고 검색
  - `keyword`: 검색어 (필수)
  - `pages`: 검색할 페이지 수 (기본: 3)

### 통계
- `GET /api/stats` - 법원별 통계
  - `pages`: 수집할 페이지 수 (기본: 3)

### 헬스체크
- `GET /health` - 서버 상태 확인

## 📖 API 문서

- Swagger UI: `/docs`
- ReDoc: `/redoc`

## 💡 사용 예시

```bash
# 공고 목록 조회
curl "https://your-app.vercel.app/api/notices?page=1&limit=5"

# 공고 상세 조회
curl "https://your-app.vercel.app/api/notices/31962"

# 검색
curl "https://your-app.vercel.app/api/search?keyword=부동산"

# 통계
curl "https://your-app.vercel.app/api/stats?pages=5"
```

## 🔧 로컬 개발

```bash
# 의존성 설치
pip install -r requirements.txt

# 서버 실행
uvicorn api.index:app --reload --port 8001

# API 문서 확인
open http://localhost:8001/docs
```

## 📁 프로젝트 구조

```
scourt-api/
├── api/
│   └── index.py      # FastAPI 메인 앱
├── vercel.json       # Vercel 설정
├── requirements.txt  # Python 의존성
└── README.md         # 문서
```

## ⚠️ 주의사항

- 대법원 사이트의 부하를 고려하여 적절한 호출 간격을 유지하세요
- 수집된 데이터는 공공 정보이나, 상업적 사용 시 관련 법규를 확인하세요

## 📄 라이선스

MIT License
