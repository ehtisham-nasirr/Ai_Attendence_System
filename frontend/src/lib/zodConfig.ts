import { z } from "zod";

// The production CSP has no 'unsafe-eval'. Zod's JIT probes with `new Function`, which the browser reports
// as a CSP violation even though Zod catches it; jitless skips the probe. Imported first in main.tsx.
z.config({ jitless: true });
