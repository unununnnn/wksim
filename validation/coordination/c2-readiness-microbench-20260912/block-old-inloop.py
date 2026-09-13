if not (live/'go.json').exists() and all((live/name/'ready.json').exists() for name in workers):
                    save(live/'go.json', clock.snapshot())

if pv and clock.tick%4 == 0:
                    for leg in (1, 2):
                        go_path = live/f'pv-go-{leg}.json'
                        ready_paths = {stack:live/stack/f'pv-ready-{leg}.json' for stack in workers}
                        if not go_path.exists() and all(path.is_file() for path in ready_paths.values()):
                            offers = {stack:json.loads(path.read_text()) for stack, path in ready_paths.items()}
                            for stack, uid in (('arducopter', 1), ('px4', 2)):
                                initial = json.loads((live/stack/'ready.json').read_text())
                                offer = offers[stack]
                                if (offer['version'] != 1 or offer['profile'] != PV_PROFILE or offer['leg'] != leg
                                        or offer['run_id'] != result['run_id'] or offer['scene_epoch'] != clock.epoch
                                        or offer['uav_id'] != uid or offer['control_epoch'] != initial['control_epoch']
                                        or len(offer['token']) != 32):
                                    raise ValueError('P+V readiness identity differs')
                            save(go_path, dict(version=1, profile=PV_PROFILE, run_id=result['run_id'],
                                scene_epoch=clock.epoch, leg=leg, issued_tick=clock.tick,
                                start_ns=(clock.tick+1000)*clock.STEP_NS, tasks=offers))
