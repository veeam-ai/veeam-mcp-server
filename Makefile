.PHONY: build clean

# Default target
all: build

# Build the Docker image
build:
	docker build -t veeam-intelligence-mcp-server .

# Clean up Docker resources
clean:
	docker rmi veeam-intelligence-mcp-server || true