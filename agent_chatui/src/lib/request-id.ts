import { v4 as uuidv4 } from "uuid";

export const REQUEST_ID_HEADER = "X-Request-ID";

export function createRequestId(): string {
  return uuidv4().replaceAll("-", "");
}

export function createRunCorrelation() {
  const requestId = createRequestId();
  return {
    requestId,
    config: {
      configurable: {
        request_id: requestId,
      },
    },
    metadata: {
      request_id: requestId,
    },
  };
}
