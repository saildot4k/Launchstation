"""Execute full audio initialization, queue ownership and reset recovery."""
from dash_sound_harness import run

run(r'''
static void ui_during_load(void) {
    int calls=rpc_calls,queued=submitted;
    assert(sound_job_id && !sound_ready && !bgm_loaded);
    ui_steps++;
    DashInput in;dashInputPollEx(&in,1);
    assert(in.any && (in.pressed & DASH_IN_DOWN));navigation_events++;
    /* Real input mapping continues while the worker owns audio/file RPC. */
    dashSoundPlay(DASH_SND_CURSOR);dashSoundApplyVolume();dashBgmSetVolume();
    dashBgmStart();dashBgmStop();dashSoundMaintain();dashSoundInit();
    char status[512];dashSoundGetStatus(status,sizeof(status));assert(strstr(status,"loading"));
    assert(calls==rpc_calls && queued==submitted);
    dashCfg.sound_vol=30;dashCfg.bgm_vol=20;
}
static void storage_job(void *unused) {
    (void)unused;assert(worker_thread && active);storage_steps++;
}
int main(void) {
    reset();during_rpc=ui_during_load;dashSoundRequestBoot();
    assert(!dashSoundInit());
    assert(q_count==1 && !module_calls && !rpc_calls && !opens && !sound_ready);
    for(int i=0;i<20;i++) {ui_steps++;dashSoundMaintain();}
    assert(submitted==1 && !module_calls); /* Slow/queued init never runs on UI. */
    settle();during_rpc=NULL;
    assert(soundAlive() && sample_uploads==8 && music_uploads==1 && ui_steps>20);
    assert(plays[DASH_SND_BOOT]==1 && plays[23]==1 && volumes[23]==20);
    for(int i=0;i<23;i++)assert(volumes[i]==30);
    assert(!sound_job_id && !sound_boot_pending && navigation_events>20);
    for(int i=0;i<20;i++)dashSoundMaintain();assert(submitted==1);
    /* Queue order serializes audio with scans/saves/artwork; never bypass it. */
    reset();dashWorkerSubmit("Storage before",1,storage_job,NULL,NULL);
    active=1;dashSoundMaintain();active=0;
    dashWorkerSubmit("Storage after",1,storage_job,NULL,NULL);
    assert(q_count==3 && !module_calls);
    finish_one();assert(storage_steps==1 && !module_calls);
    finish_one();assert(soundAlive() && module_calls==2 && storage_steps==1);
    finish_one();assert(storage_steps==2);
    /* Foreground RPC and IOP reset guards defer submission without blocking. */
    reset();foreground_io=1;dashSoundMaintain();assert(!submitted);
    foreground_io=0;parked=1;dashSoundMaintain();assert(!submitted);
    parked=0;reject_submit=1;dashSoundMaintain();assert(!submitted && !sound_job_id);
    reject_submit=0;dashSoundMaintain();assert(submitted==1);settle();assert(soundAlive());
    /* A launch/shutdown drains queued initialization and suppresses boot playback. */
    reset();dashSoundRequestBoot();dashSoundMaintain();dashSoundShutdown();
    assert(!q_count && !sound_job_id && !sound_ready && !sound_boot_pending && !allocations);
    assert(quits==1 && stops==1 && !plays[DASH_SND_BOOT] && !plays[23]);
    /* Stale queued results never invoke old-generation RPC or publish samples. */
    reset();dashSoundMaintain();generation++;settle();
    assert(!sound_ready && !module_calls && !rpc_calls && !allocations);
    dashSoundMaintain();settle();assert(soundAlive());
    /* Forget an already reset IOP without contacting its destroyed server. */
    generation++;int before=rpc_calls;dashSoundShutdown();assert(before==rpc_calls);
    dashSoundMaintain();settle();assert(soundAlive());
    /* All-SFX failure leaves the healthy service usable by independent BGM. */
    reset();sample_failures=DASH_SND_COUNT;dashSoundMaintain();settle();
    assert(soundAlive() && warnings==1 && plays[23]==1);
    for(int i=0;i<DASH_SND_COUNT;i++)assert(!samples[i].buffer);
    /* Real failures are attempted once per IOP generation, then recover. */
    for(int failure=0;failure<4;failure++) {
        reset();module_failure=failure<2?failure+1:0;init_failure=failure==2;adpcm_failure=failure==3;
        dashSoundMaintain();settle();assert(!soundAlive() && warnings==1 && !plays[23]);
        int attempts=submitted;
        for(int i=0;i<20;i++)dashSoundMaintain();assert(submitted==attempts);
        module_failure=init_failure=adpcm_failure=0;generation++;
        dashSoundMaintain();settle();assert(soundAlive() && plays[23]==1);
    }
    reset();dashCfg.sound=dashCfg.bgm=0;dashSoundMaintain();settle();
    assert(soundAlive() && module_calls==2 && plays[23]==1 && volumes[23]==10);
    reset();
    puts("PASS: background-only module/sample/music loading, UI RPC exclusion, settings snapshots, queue serialization, startup cue, shutdown draining, failures and reset generations");
    return 0;
}
''', 'recovery', navigation=True)
