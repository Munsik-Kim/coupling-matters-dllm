PYTHON ?= python3

.PHONY: verify test paper manifest

verify:
	$(PYTHON) scripts/verify_public_release.py --root .

test:
	PYTHONPATH=tools/event_addressed_rng:. $(PYTHON) -m unittest discover -s tools/coupling_audit -p 'test_*.py'
	PYTHONPATH=tools/event_addressed_rng:. $(PYTHON) -m unittest discover -s tools/split_damage_analysis -p 'test_*.py'

paper:
	bash scripts/build_paper.sh

manifest:
	$(PYTHON) scripts/generate_manifest.py --root .
