import { defineConfig } from "orval";

// `npm run gen-api` (or `make gen-api` from the repo root) regenerates src/api/generated from the
// backend's OpenAPI spec. Never edit the generated files by hand (standards/08).
export default defineConfig({
  facetrack: {
    input: { target: "../docs/openapi.yaml" },
    output: {
      mode: "split",
      target: "src/api/generated/endpoints.ts",
      schemas: "src/api/generated/model",
      client: "axios-functions",
      clean: true,
      override: {
        mutator: { path: "src/api/client.ts", name: "apiRequest" },
        useDates: false,
      },
    },
  },
});
