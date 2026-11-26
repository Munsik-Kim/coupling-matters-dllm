Coupling Matters · 에이전트 평가 검증
2026-11-26

실행
  ZIP을 풀고 파일이 있는 디렉터리에서 아래 명령을 실행합니다.
  python run_checks.py
  Windows Python Launcher에서는 py -3 run_checks.py 로 실행할 수 있습니다.
  Python 3.8 이상 표준 라이브러리만 필요합니다. GPU, 네트워크, 모델 가중치는 필요하지 않습니다.
  세 번의 PASS는 모든 산출값이 보관된 정확 계산과 같음을 뜻합니다.

읽을 자료
  Coupling_Matters_Agent_Report_KO.md       보고서 한국어 원문
  coupling_agent_exact.py / .json          12×12 경로, 세 규칙, 네 지표, 최초 분기, 두 종류의 단계 개입
  counterexamples.py / .json               국소 최대 일치 반례, 비동기 난수 반례, 주 모형의 온라인 달성 경계
  case017_pairs.csv                        원장에서 계산에 필요한 24개 과제와 두 조건의 지표만 투영한 표
  audit_case017.py / case017_counts.json    원장 투영과 00,01,10,11 재집계
  run_checks.py                            모든 계산과 보관 결과의 일치 여부 확인

모형 수치의 분모는 단일하게 고정한 모의 과제에서 짝지은 전체 실행의 확률질량입니다.
Case017의 분모는 공개된 서로 다른 24개 과제 ID입니다.
분수는 JSON에 문자열로 저장합니다. 복수 단계 중 처음 다른 라벨의 집계는 공동확률입니다.

Case017 공개 원장으로부터 24쌍을 직접 재생성하려면 원본 CSV를 내려받아 실행합니다.
  python audit_case017.py episode_ledger.csv --write-pairs regenerated_pairs.csv
  입력 파일 SHA-256 검증 → stage=P2, kv=K1, policy in {C0,G} → 과제 ID로 짝짓기 → 네 지표 검산.
  최신 검증 관측은 원 프로젝트의 사후 지표입니다. 이 작업은 공개 원장의 산술 검산이며 원 실행의 재현과 구별합니다.

고정 버전 원장
https://github.com/Munsik-Kim/inference-lab/blob/9ca5eee3da47c552f02d7eaa7b7a6393fb3f2d17/cases/017-agent-contract-cost-bench/publication/summary/episode_ledger.csv
SHA-256 35f689590df844332348f99c50f9ce0fb28fe12f9b816e0a196cf3d3ebae2b2a
원 프로젝트의 보고서, 검증 규칙 및 확장 기준 이탈 문서는 같은 커밋의 REPORT.md, PROTOCOL.md, PROTOCOL_DEVIATION.md에 있습니다.
