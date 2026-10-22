# Coupling Matters — 한국어 안내

빈칸을 채워 가며 문장을 만드는 모델에서, 저비트 변경으로 생긴 차이가 최종 출력까지 어떻게 퍼지는지 분석했습니다. 두 실행의 난수를 맞춰 비교하는 코드, 오차의 상한을 계산하는 수학적 결과, CPU 검산 도구를 제공합니다.

**프리프린트 / 기술 보고서이며 동료평가를 거치지 않았습니다.**

저자: Munsik Kim — Independent Researcher, Republic of Korea  
Zenodo: https://zenodo.org/records/21880649  
DOI: https://doi.org/10.5281/zenodo.21880649

난수를 맞추는 방식은 coupling이라고 하며, 이 선택에 따라 측정되는 오차 상한도 달라집니다. 저장소에는 기술 보고서, 공개 가능한 소규모 근거 자료, 모델 없이 실행하는 검산 코드, 감사 기록과 부정 결과가 있습니다.

핵심 정리는 monotone MASK→token, committed-token copy-only 가정 아래 첫 분기 시점의 남은 mask 질량으로 이후 normalized Hamming 왜곡을 상계합니다. 구현된 coordinatewise maximal coupling은 유효한 product coupling이지만 joint-optimal 또는 Wasserstein-optimal coupling이라고 주장하지 않습니다.

빠른 검증:

```bash
make verify
make test
make paper
```

기본 테스트는 모델·데이터 다운로드 없이 CPU에서 실행됩니다. 전체 GPU 실험 재실행에는 외부 공개 모델과 데이터, 계산 자원, 공개 저장소에 포함하지 않은 대형 원시 artifact가 필요합니다. 한계와 재현성 단계는 [`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md), [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md)를 참고하십시오.
