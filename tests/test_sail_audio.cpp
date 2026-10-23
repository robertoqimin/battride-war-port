#include "sail_audio.hpp"
#include <cassert>
#include <iostream>
int main(int argc,char** argv) {
    assert(argc==2 || argc==3);using namespace port_sail;
    PamfAudio meta;assert(meta.probe(argv[1]));assert(meta.present && meta.channels==2 && meta.rate==48000);
    AudioDecoder decoder;decoder.start(argv[1],meta);uint64_t total=0;double energy=0,peak=0;
    auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(20);std::vector<float> pcm;int code=0;
    while(std::chrono::steady_clock::now()<deadline) {
        unsigned n=decoder.read(256,meta.channels,pcm);total+=n;
        for(float x:pcm){assert(std::isfinite(x));energy+=double(x)*x;peak=std::max(peak,std::abs(double(x)));}
        if(decoder.done(code))break;
        if(!n)std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
    assert(decoder.done(code)&&code==0);assert(total==(argc==3?std::stoull(argv[2]):6533120));assert(peak>0.1 && peak<2);
    std::cout<<"PAMF ATRAC3plus: samples="<<total<<" rms="<<sqrt(energy/(total*2))<<" peak="<<peak<<" PASS\n";
    AudioDecoder cancel;cancel.start(argv[1],meta);std::this_thread::sleep_for(std::chrono::milliseconds(250));
    auto begin=std::chrono::steady_clock::now();cancel.stop();assert(std::chrono::steady_clock::now()-begin<std::chrono::seconds(2));
    std::cout<<"Audio cancellation with full PCM queue: PASS\n";
    // A valid private PES with a truncated ATRAC-X frame must fail, without
    // manufacturing PCM or reporting successful end of stream.
    char temp[]="/tmp/sail-malformed.XXXXXX";int fd=mkstemp(temp);assert(fd>=0);
    FILE* file=fdopen(fd,"wb");assert(file);
    std::array<uint8_t,2048> header{};memcpy(header.data(),"PAMF0041",8);
    header[11]=1;header[0x6F]=1;header[0x81]=1;header[0x87]=1;
    header[0x88]=0xDC;header[0x8C]=0xBD;header[0x9A]=2;header[0x9B]=1;
    const uint8_t pes[]={0,0,1,0xBD,0,15,0x80,0,0,0,0,0,0,0x0F,0xD0,0x48,0x55,0,0,0,0};
    fwrite(header.data(),1,header.size(),file);fwrite(pes,1,sizeof pes,file);fclose(file);
    PamfAudio bad_meta;assert(bad_meta.probe(temp)&&bad_meta.present);
    AudioDecoder bad;bad.start(temp,bad_meta);deadline=std::chrono::steady_clock::now()+std::chrono::seconds(2);
    while(!bad.done(code)&&std::chrono::steady_clock::now()<deadline)std::this_thread::sleep_for(std::chrono::milliseconds(1));
    assert(bad.done(code)&&code!=0);pcm.assign(8,1);assert(bad.read(256,2,pcm)==0&&pcm.empty());
    unlink(temp);std::cout<<"Truncated private ATRAC-X frame rejected: PASS\n";
}
