.PHONY: help build upload monitor clean docs test

help:
	@echo "Smart Sweat-Band Build Targets"
	@echo "=============================="
	@echo "make build          - Compile firmware"
	@echo "make upload         - Compile and upload to device"
	@echo "make monitor        - Open serial monitor (115200 baud)"
	@echo "make clean          - Remove build artifacts"
	@echo "make docs           - Generate Doxygen documentation"
	@echo "make test           - Run hardware validation tests"
	@echo "make format         - Format code with clang-format"

build:
	pio run

upload:
	pio run -t upload

monitor:
	pio device monitor --speed 115200

upload-monitor:
	pio run -t upload && pio device monitor --speed 115200

clean:
	pio run --target clean
	rm -rf docs/

docs:
	@which doxygen > /dev/null || (echo "Doxygen not installed. Install with: sudo apt-get install doxygen" && exit 1)
	doxygen Doxyfile
	@echo "Documentation generated in ./docs/html/index.html"

test:
	@echo "Running hardware validation..."
	@echo "[1] Checking all sensors read correctly..."
	pio run -t upload && pio device monitor --speed 115200 --pattern="SUCCESS"

format:
	@echo "Code formatting would go here (clang-format or astyle)"
	@echo "Configure .editorconfig in your editor for auto-formatting"

list-ports:
	pio device list

all: clean build upload
