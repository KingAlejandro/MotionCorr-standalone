/* MotionCorr file content identity controls. Copyright (C) 2026 contributors.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "src/processing_file_digest.h"
#include <array>
#include <cerrno>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iostream>
#include <stdexcept>
#include <string>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <vector>

using namespace motioncorr_identity;
namespace fs=std::filesystem;

#if defined(PROCESSING_FILE_DIGEST_FAULT_WRAPS) && defined(__linux__)
// Deterministic OS-error doubles at the actual production calls, device-free.
// These controls are separate from ordinary real-file positives below.
enum class Fault { None, ReadError, FstatError, StatError, ShortEof, DescriptorChange, PathChange, InterruptedRead };
static Fault fault=Fault::None;
static unsigned fstat_calls=0,read_calls=0,stat_calls=0;
extern "C" ssize_t __real_read(int,void *,size_t);
extern "C" int __real_fstat(int,struct stat *);
extern "C" int __real_stat(const char *,struct stat *);
extern "C" ssize_t __wrap_read(int fd,void *buffer,size_t n)
{
    ++read_calls;
    if(fault==Fault::ReadError){errno=EIO;return -1;}
    if(fault==Fault::ShortEof)return 0;
    if(fault==Fault::InterruptedRead && read_calls==1){errno=EINTR;return -1;}
    return __real_read(fd,buffer,n);
}
extern "C" int __wrap_fstat(int fd,struct stat *s)
{
    ++fstat_calls;
    if(fault==Fault::FstatError){errno=EIO;return -1;}
    const int rc=__real_fstat(fd,s);
    if(rc==0 && fault==Fault::DescriptorChange && fstat_calls==2)++s->st_ctim.tv_nsec;
    return rc;
}
extern "C" int __wrap_stat(const char *path,struct stat *s)
{
    ++stat_calls;
    if(fault==Fault::StatError){errno=EIO;return -1;}
    const int rc=__real_stat(path,s);
    if(rc==0 && fault==Fault::PathChange)++s->st_ino;
    return rc;
}
#endif

namespace
{
unsigned passed=0;
void require(bool ok,const std::string &why)
{
    if(!ok)throw std::runtime_error("FAIL "+why);
    ++passed;std::cout<<"PASS "<<why<<'\n';
}
void reject(const std::string &name,const std::function<void()> &action,const std::string &path)
{
    bool threw=false;
    try { action(); }
    catch(const std::runtime_error &e)
    {
        threw=true;require(std::string(e.what()).find(path)!=std::string::npos,name+" names path");
    }
    require(threw,name+" refuses rather than returns identity");
}
struct Temp
{
    fs::path path;
    Temp()
    {
        std::string name=(fs::temp_directory_path()/"motioncorr-digest-XXXXXX").string();
        std::vector<char> writable(name.begin(),name.end());writable.push_back('\0');
        char *result=::mkdtemp(writable.data());
        if(!result)throw std::runtime_error("mkdtemp failed");
        path=result;
    }
    ~Temp() { std::error_code ignored;fs::remove_all(path,ignored); }
};
void write(const fs::path &path,const std::vector<unsigned char> &bytes)
{
    std::ofstream f(path,std::ios::binary|std::ios::trunc);
    if(!f)throw std::runtime_error("test fixture open failed: "+path.string());
    f.write(reinterpret_cast<const char *>(bytes.data()),static_cast<std::streamsize>(bytes.size()));
    f.close();if(!f)throw std::runtime_error("test fixture write failed: "+path.string());
}
void restoreMtime(const fs::path &path,const FileSnapshot &old)
{
    struct timespec times[2]={{0,UTIME_OMIT},{old.mtime_seconds,old.mtime_nanoseconds}};
    if(::utimensat(AT_FDCWD,path.c_str(),times,0)!=0)throw std::runtime_error("utimensat failed");
}
}

int main()
{
    try
    {
        Temp tmp;
        require(sha256Bytes(nullptr,0)=="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855","SHA256 empty FIPS vector");
        require(sha256Bytes("abc",3)=="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad","SHA256 abc FIPS vector");
        const std::string million(1000000,'a');
        require(sha256Bytes(million.data(),million.size())=="cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0","SHA256 million-a FIPS vector");
        bool null_threw=false;try { sha256Bytes(nullptr,1); }catch(const std::runtime_error &){null_threw=true;}
        require(null_threw,"SHA256 null nonempty bytes refused");
        // Frozen independent Python hashlib references, data[i]=i%251. Boundary
        // sizes power SHA padding/blocks and production64KiB streaming, rather
        // than comparing two calls of the same implementation to one another.
        const std::array<std::pair<size_t,const char *>,11> vectors{{
            {0,"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"},
            {1,"6e340b9cffb37a989ca544e6bb780a2c78901d3fb33738768511a30617afa01d"},
            {55,"463eb28e72f82e0a96c0a4cc53690c571281131f672aa229e0d45ae59b598b59"},
            {56,"da2ae4d6b36748f2a318f23e7ab1dfdf45acdc9d049bd80e59de82a60895f562"},
            {63,"29af2686fd53374a36b0846694cc342177e428d1647515f078784d69cdb9e488"},
            {64,"fdeab9acf3710362bd2658cdc9a29e8f9c757fcf9811603a8c447cd1d9151108"},
            {65,"4bfd2c8b6f1eec7a2afeb48b934ee4b2694182027e6d0fc075074f2fabb31781"},
            {65535,"dda402a2c028f0cbbdbc5c6ebae965eed9c75f71236e7022b0386d3455d5ae2f"},
            {65536,"4b640d85ab3ba30fd02c9fc9db4a8928f416322ad27022ea58a65aaee68a4df2"},
            {65537,"237356e18b503616912abb8ffaed3a72591e397d4ac294c4637917d48a3f529d"},
            {131079,"14959b78e9a3db42d9708e444df7e55a1af4584ec8b4f967b009843c3fb738d3"}
        }};
        const fs::path file=tmp.path/"file.bin";
        for(const auto &v:vectors)
        {
            std::vector<unsigned char> bytes(v.first);
            for(size_t i=0;i<bytes.size();++i)bytes[i]=static_cast<unsigned char>(i%251);
            require(sha256Bytes(bytes.data(),bytes.size())==v.second,"independent byte vector "+std::to_string(v.first));
            write(file,bytes);const FileDigest result=digestFile(file.string());
            require(result.sha256==v.second,"actual streamed file vector "+std::to_string(v.first));
            require(result.snapshot==snapshotFile(file.string()) && result.snapshot.size==v.first,"streamed file snapshot "+std::to_string(v.first));
        }
        write(file,{'a','b','c'});const FileDigest old=digestFile(file.string());
        requireUnchanged(file.string(),old.snapshot);require(true,"unchanged actual file accepted");
        for(unsigned field=0;field<7;++field)
        {
            FileSnapshot changed=old.snapshot;
            switch(field)
            {
                case 0:++changed.device;break;case 1:++changed.inode;break;case 2:++changed.size;break;
                case 3:++changed.mtime_seconds;break;case 4:++changed.mtime_nanoseconds;break;
                case 5:++changed.ctime_seconds;break;case 6:++changed.ctime_nanoseconds;break;
            }
            require(changed!=old.snapshot,"snapshot dimension "+std::to_string(field)+" participates");
            reject("snapshot dimension "+std::to_string(field),[&]{requireUnchanged(file.string(),changed);},file.string());
        }
        ::usleep(2000);write(file,{'x','y','z'});restoreMtime(file,old.snapshot);
        const FileDigest rewritten=digestFile(file.string());
        require(rewritten.snapshot.size==old.snapshot.size && rewritten.snapshot.mtime_seconds==old.snapshot.mtime_seconds && rewritten.snapshot.mtime_nanoseconds==old.snapshot.mtime_nanoseconds,"same-size same-mtime rewrite fixture genuinely matches");
        require(rewritten.sha256!=old.sha256,"same-size same-mtime rewrite content digest changes");
        reject("same-size same-mtime rewrite ctime invalidation",[&]{requireUnchanged(file.string(),old.snapshot);},file.string());
        const fs::path next=tmp.path/"replacement";write(next,{'a','b','c'});restoreMtime(next,rewritten.snapshot);fs::rename(next,file);
        const FileSnapshot replacement=snapshotFile(file.string());
        require(replacement.inode!=rewritten.snapshot.inode,"actual pathname replacement changes inode");
        reject("actual pathname replacement",[&]{requireUnchanged(file.string(),rewritten.snapshot);},file.string());
        const fs::path link=tmp.path/"alias";fs::create_symlink(file,link);
        require(digestFile(link.string()).sha256==old.sha256,"regular symlink content identity accepted");
        const fs::path missing=tmp.path/"missing";
        reject("missing file digest",[&]{digestFile(missing.string());},missing.string());
        reject("directory digest",[&]{digestFile(tmp.path.string());},tmp.path.string());
        reject("directory snapshot",[&]{snapshotFile(tmp.path.string());},tmp.path.string());
        const fs::path fifo=tmp.path/"fifo";
        if(::mkfifo(fifo.c_str(),0600)!=0)throw std::runtime_error("mkfifo failed");
        reject("FIFO digest without blocking open",[&]{digestFile(fifo.string());},fifo.string());
        bool nul_threw=false;try { digestFile(std::string("missing\0suffix",14)); }catch(const std::runtime_error &){nul_threw=true;}
        require(nul_threw,"embedded NUL refuses truncated OS pathname");
        const std::string executable=executablePath();
        require(!executable.empty() && executable[0]=='/',"actual executable identity path absolute");
        require(digestFile(executable).sha256.size()==64,"actual loaded executable file can be digested");
#if defined(PROCESSING_FILE_DIGEST_FAULT_WRAPS) && defined(__linux__)
        for(const auto &item:std::array<std::pair<Fault,const char *>,6>{{
            {Fault::ReadError,"injected read EIO"},{Fault::FstatError,"injected fstat EIO"},
            {Fault::StatError,"injected final pathname stat EIO"},{Fault::ShortEof,"injected short EOF"},
            {Fault::DescriptorChange,"injected post-read descriptor ctime change"},{Fault::PathChange,"injected final pathname inode change"}}})
        {
            fault=item.first;fstat_calls=read_calls=stat_calls=0;
            reject(item.second,[&]{digestFile(file.string());},file.string());
            fault=Fault::None;
        }
        fault=Fault::InterruptedRead;fstat_calls=read_calls=stat_calls=0;
        const FileDigest interrupted=digestFile(file.string());fault=Fault::None;
        require(read_calls>=3 && interrupted.sha256==old.sha256,"actual production read retries EINTR then completes exact digest");
        std::cout<<"LINUX_OS_FAULT_BOUNDARIES_COMPLETE\n";
#endif
        std::cout<<"PROCESSING_FILE_DIGEST_COMPLETE checks="<<passed<<'\n';return 0;
    }
    catch(const std::exception &e) { std::cerr<<e.what()<<'\n';return 1; }
}
