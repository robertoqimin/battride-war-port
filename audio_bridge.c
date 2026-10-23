// Keep the SDK audio state/HLE intact; supply a device-paced POSIX mixer loop.
#include <pthread.h>
#include <time.h>
static int port_audio_thread_create(pthread_t*,const pthread_attr_t*,void*(*)(void*),void*);
#define pthread_create port_audio_thread_create
#include PORT_AUDIO_SOURCE
#undef pthread_create
static unsigned long long port_audio_ns(void) {
    struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);
    return (unsigned long long)t.tv_sec*1000000000ull+t.tv_nsec;
}
static void* port_audio_mix(void* unused) {
    (void)unused;
    unsigned long long epoch=port_audio_ns(),blocks=0;
    unsigned report=0;int peak_on=getenv("AUDIO_PEAK")!=NULL;
    const char* path=getenv("AUDIO_WAV");FILE* dump=path?fopen(path,"wb"):NULL;
    fprintf(stderr,"[port-audio] POSIX mixer paced to the output device, 48000 Hz\n");
    while(s_mix_thread_running) {
        int room=audio_backend_room();
        if(room>=0 && room<CELL_AUDIO_BLOCK_SAMPLES){audio_backend_wait();continue;}
        if(room<0) {
            unsigned long long now=port_audio_ns(),due=epoch+blocks*CELL_AUDIO_BLOCK_SAMPLES*1000000000ull/CELL_AUDIO_SAMPLE_RATE;
            if(now<due) {struct timespec delay={0,1000000};nanosleep(&delay,NULL);continue;}
            if(now-due>50000000)epoch=now-blocks*CELL_AUDIO_BLOCK_SAMPLES*1000000000ull/CELL_AUDIO_SAMPLE_RATE;
        }
        audio_mix_one_block();blocks++;
        if(dump)fwrite(s_mix_buffer,sizeof(float),CELL_AUDIO_BLOCK_SAMPLES*2,dump);
        if(peak_on && ++report%200==0) {
            float peak=0;for(unsigned i=0;i<CELL_AUDIO_BLOCK_SAMPLES*2;i++){float x=fabsf(s_mix_buffer[i]);if(x>peak)peak=x;}
            fprintf(stderr,"[port-audio] mixed blocks=%llu peak=%.5f queued=%u\n",blocks,peak,audio_backend_queued_samples());
        }
        audio_backend_submit(s_mix_buffer,CELL_AUDIO_BLOCK_SAMPLES);
        audio_notify_event_queues();
    }
    if(dump)fclose(dump);
    return NULL;
}
static int port_audio_thread_create(pthread_t* t,const pthread_attr_t* attr,void*(*fn)(void*),void* arg) {
    return pthread_create(t,attr,fn==audio_mix_thread_func?port_audio_mix:fn,arg);
}
