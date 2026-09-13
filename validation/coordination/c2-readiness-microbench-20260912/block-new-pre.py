go_path_initial = live/'go.json'
ready_paths_initial = {name:live/name/'ready.json' for name in workers}
pv_go_paths = {leg:live/f'pv-go-{leg}.json' for leg in (1, 2)}
pv_ready_paths = {leg:{stack:live/stack/f'pv-ready-{leg}.json' for stack in workers}
                              for leg in (1, 2)}
