---
description: Start the Aperio v2 bounded project loop
---

# /aperio

Load the Aperio skill and use its bounded loop:

1. Record the owner's request with `aperio ask`.
2. Inspect the target before planning.
3. Write the smallest plan that satisfies the request.
4. Ask the owner to approve it. Do not self-approve.
5. Apply it with `aperio run`.
6. Run the acceptance checks with `aperio verify`.
7. Obtain a different reviewer with `aperio review <task-id> --host claude`, or record a manual verdict from a reviewer who is not the builder.
8. Finish with `aperio done` only after a confirmed review.
9. Write the handoff with `aperio handoff`.

Do not run an unapproved plan. Do not write outside the plan's allowed paths. Do not claim a host, deployment, or target-project delivery works unless you ran it.
