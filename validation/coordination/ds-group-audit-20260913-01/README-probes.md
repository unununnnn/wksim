# One-off reconnaissance probes used while designing the audit invariants.
#
# These are kept only as a record of how the validation rules were derived from
# the real archive (report fields, boundary agreement, native-wait containment,
# over-budget set and dropped reports).  They are NOT part of the audit tool and
# NOT part of the test suite; run them only by hand against a read-only archive.
#
#   wsl -d Ubuntu-22.04 -e bash -lc \
#     'python3 recon_probe.py  /root/wksim-release-acceptance-fe3/validation/joint-public-flight-rfw9nmbb'
#   wsl -d Ubuntu-22.04 -e bash -lc \
#     'python3 recon_probe2.py /root/wksim-release-acceptance-fe3/validation/joint-public-flight-rfw9nmbb'
