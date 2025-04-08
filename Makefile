.PHONY: build run

# Default target
all: build

# Build the Docker image
build:
	docker build -t veeam-mcp .

# Clean up Docker resources
clean:
	docker rmi veeam-mcp || true 