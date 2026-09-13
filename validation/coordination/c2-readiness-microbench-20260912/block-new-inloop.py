if not go_path_initial.exists() and all(path.exists() for path in ready_paths_initial.values()):
                    save(go_path_initial, clock.snapshot())

if pv and clock.tick%4 == 0:
                    for leg in (1, 2):
                        if not pv_go_paths[leg].exists() and all(path.is_file() for path in pv_ready_paths[leg].values()):
                            offers = {stack:json.loads(path.read_text()) for stack, path in pv_ready_paths[leg].items()}
                            for stack, uid in (('arducopter', 1), ('px4', 2)):
                                initial = json.loads((live/stack/'ready.json').read_text())
                                offer = offers[stack]
                                if (offer['version'] != 1 or offer['profile'] != PV_PROFILE or offer['leg'] != leg
                                        or offer['run_id'] != result['run_id'] or offer['scene_epoch'] != clock.epoch
                                        or offer['uav_id'] != uid or offer['control_epoch'] != initial['control_epoch']
                                        or len(offer['token']) != 32):
                                    raise ValueError('P+V readiness identity differs')
                            save(pv_go_paths[leg], dict(version=1, profile=PV_PROFILE, run_id=result['run_id'],
                                scene_epoch=clock.epoch, leg=leg, issued_tick=clock.tick,
                                start_ns=(clock.tick+1000)*clock.STEP_NS, tasks=offers))
