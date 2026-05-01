WORKERS := $(shell python3 -c "import os; print(max(1, (os.cpu_count() or 1)//3)+1)")

all:
	@HF_HUB_VERBOSITY=error HF_HUB_DISABLE_PROGRESS_BARS=1 granian --interface asgi \
			--host 0.0.0.0 \
			--port 8081 \
			--loop uvloop \
			--no-reload \
			--no-ws \
			--metrics \
			endpoint:app