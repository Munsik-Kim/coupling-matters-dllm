# Coupling Matters — 한국어 안내

**프리프린트 / 기술 보고서이며 동료평가를 거치지 않았습니다.**

저자: Munsik Kim — Independent Researcher, Republic of Korea  
Zenodo: https://zenodo.org/records/21880649  
DOI: https://doi.org/10.5281/zenodo.21880649

이 공개 저장소는 양자화된 masked diffusion language model의 유한 지평 transport 안정성을 coupling 관점에서 분석한 연구 개요서입니다. 기술 보고서, 공개 가능한 compact evidence, CPU/model-free 검증 코드, 독립 감사 결과, 음성 결과, 재사용 가능한 실험 기법을 포함합니다.

핵심 정리는 monotone MASK→token, committed-token copy-only 가정 아래 첫 분기 시점의 남은 mask 질량으로 이후 normalized Hamming 왜곡을 상계합니다. 구현된 coordinatewise maximal coupling은 유효한 product coupling이지만 joint-optimal 또는 Wasserstein-optimal coupling이라고 주장하지 않습니다.

빠른 검증:

```bash
make verify
make test
make paper
```

기본 테스트는 모델·데이터 다운로드 없이 CPU에서 실행됩니다. 전체 GPU 실험 재실행에는 외부 공개 모델과 데이터, 계산 자원, 공개 저장소에 포함하지 않은 대형 원시 artifact가 필요합니다. 한계와 재현성 단계는 [`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md), [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md)를 참고하십시오.
