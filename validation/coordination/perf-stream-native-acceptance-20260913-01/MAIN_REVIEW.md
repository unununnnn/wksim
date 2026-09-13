# Native admission is not yet accepted

The first real compile used the source snapshots and SHA256 values in
`receipt.json`. It failed with two `-Werror=format-truncation` diagnostics in
`record_error` and `settle_errors`. No demo or fault case executed. Do not
disable the warning to declare the recorder build accepted.

Additional source findings to resolve before native admission:

- `join_reader` treats ESRCH as successful join, sets `reader_joined=true`,
  and permits freeing resources. Every nonzero join result must instead retain
  ownership and fail. `join_failure_case.c` directly tests this helper without
  creating any thread or perf event.
- `start_abort` describes an intentional leak on failed join and gives the
  caller no retained handle. The API needs an explicit recoverable ownership
  result for this exceptional path; it cannot claim all failed starts release
  everything while hiding retained live resources.
- Policy readiness is synchronized, but the false policy result is rejected
  after RESET/ENABLE. Reject it before enabling the event.
- Initialized mutexes and the condition variable are freed without destroy.
  Track successful initialization and destroy them after successful join,
  including partial initialization and create-failure paths.

`create_failure_case.c` is a main-owned linker-injected pthread_create failure
test. It requires explicit SCHED_OTHER attributes, propagated EAGAIN, a null
handle and unchanged self FD/thread counts. It has not run yet because the
required build failed first.

The separate final-loss/sentinel protocol remains unimplemented. Fixing these
startup/cleanup issues or passing a short demo does not prove stream
completeness and does not authorize flight wiring.
