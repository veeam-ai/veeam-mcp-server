# End-to-End Tests

This directory contains end-to-end tests for the Veeam MCP Server.

## Setup

1. **Copy the environment template:**
   ```bash
   cp .env.test.example .env.test
   ```

2. **Configure environment variables in `.env.test`:**
   - Set `ACCEPT_SELF_SIGNED_CERT=true` for development/test environments
   - Add any other required environment variables (Veeam server URLs, API keys, etc.)

3. **Load environment variables before running tests:**
   ```bash
   export $(cat .env.test | xargs)
   ```

## Running E2E Tests

Run all end-to-end tests:
```bash
npm run test:e2e
```

Run specific e2e test:
```bash
npm run test:e2e -- debug.e2e.test.ts
```

## Test Structure

### debug.e2e.test.ts
This test validates the main entry point logic from [debug.ts](../../debug.ts):
- Sets up required environment variables
- Executes the `answerQuestion` function
- Validates successful completion
- Checks that logging occurs throughout the execution

**Validation Conditions:**
- Function runs to completion without errors
- Returns expected result structure (message and artifacts)
- Logging messages are produced (proves execution flow)

## Adding New E2E Tests

1. Create a new test file with the `.e2e.test.ts` extension
2. Set up necessary environment variables in `beforeAll` hook
3. Test your entry point or integration scenario
4. Validate that the test runs till the end successfully

## Notes

- E2E tests are excluded from regular test runs (they require real Veeam server connections)
- Default timeout is 30 seconds (configurable in jest.e2e.config.js)
- Tests should clean up resources (disconnect clients, etc.)
