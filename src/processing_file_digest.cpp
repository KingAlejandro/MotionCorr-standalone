/* MotionCorr file content identity. Copyright (C) 2026 MotionCorr contributors.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "src/processing_file_digest.h"
#include <array>
#include <cerrno>
#include <cstring>
#include <fcntl.h>
#include <limits>
#include <stdexcept>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>
#ifdef __APPLE__
#include <mach-o/dyld.h>
#include <cstdlib>
#endif

namespace motioncorr_identity
{
namespace
{
std::runtime_error error(const std::string &path, const std::string &why)
{
    return std::runtime_error("Cannot establish file identity for " + path + ": " + why);
}
void validPath(const std::string &path)
{
    if (path.empty() || path.find('\0') != std::string::npos)
        throw error(path, "empty path or embedded NUL");
}
struct Descriptor
{
    int fd;
    const std::string &path;
    explicit Descriptor(const std::string &name) : fd(-1), path(name)
    {
        validPath(path);
        // O_NONBLOCK prevents a malformed FIFO path from hanging before fstat
        // can refuse its type. It does not change regular-file read semantics.
        do { fd = ::open(path.c_str(), O_RDONLY | O_CLOEXEC | O_NONBLOCK); }
        while (fd < 0 && errno == EINTR);
        if (fd < 0) throw error(path, "open: " + std::string(std::strerror(errno)));
    }
    ~Descriptor() { if (fd >= 0) ::close(fd); }
    Descriptor(const Descriptor &) = delete;
    Descriptor &operator=(const Descriptor &) = delete;
    void closeChecked()
    {
        const int old = fd;
        fd = -1; // Never retry close on a potentially recycled descriptor.
        if (::close(old) != 0) throw error(path, "close: " + std::string(std::strerror(errno)));
    }
};
FileSnapshot fromStat(const std::string &path, const struct stat &s)
{
    if (!S_ISREG(s.st_mode) || s.st_size < 0) throw error(path, "not a regular file with nonnegative size");
#ifdef __APPLE__
    const struct timespec m = s.st_mtimespec, c = s.st_ctimespec;
#else
    const struct timespec m = s.st_mtim, c = s.st_ctim;
#endif
    return {static_cast<uint64_t>(s.st_dev), static_cast<uint64_t>(s.st_ino),
            static_cast<uint64_t>(s.st_size), m.tv_sec, m.tv_nsec, c.tv_sec, c.tv_nsec};
}
FileSnapshot descriptorSnapshot(const Descriptor &d)
{
    struct stat s{};
    if (::fstat(d.fd, &s) != 0) throw error(d.path, "fstat: " + std::string(std::strerror(errno)));
    return fromStat(d.path, s);
}
FileSnapshot pathnameSnapshot(const std::string &path)
{
    struct stat s{};
    if (::stat(path.c_str(), &s) != 0) throw error(path, "stat after read: " + std::string(std::strerror(errno)));
    return fromStat(path, s);
}

class Sha256
{
    std::array<uint32_t,8> state_{{0x6a09e667u,0xbb67ae85u,0x3c6ef372u,0xa54ff53au,
                                 0x510e527fu,0x9b05688cu,0x1f83d9abu,0x5be0cd19u}};
    std::array<unsigned char,64> block_{};
    size_t used_ = 0;
    uint64_t bytes_ = 0;
    static uint32_t rotate(uint32_t value, unsigned n) { return (value >> n) | (value << (32-n)); }
    void compress()
    {
        static constexpr uint32_t k[64] = {
            0x428a2f98u,0x71374491u,0xb5c0fbcfu,0xe9b5dba5u,0x3956c25bu,0x59f111f1u,0x923f82a4u,0xab1c5ed5u,
            0xd807aa98u,0x12835b01u,0x243185beu,0x550c7dc3u,0x72be5d74u,0x80deb1feu,0x9bdc06a7u,0xc19bf174u,
            0xe49b69c1u,0xefbe4786u,0x0fc19dc6u,0x240ca1ccu,0x2de92c6fu,0x4a7484aau,0x5cb0a9dcu,0x76f988dau,
            0x983e5152u,0xa831c66du,0xb00327c8u,0xbf597fc7u,0xc6e00bf3u,0xd5a79147u,0x06ca6351u,0x14292967u,
            0x27b70a85u,0x2e1b2138u,0x4d2c6dfcu,0x53380d13u,0x650a7354u,0x766a0abbu,0x81c2c92eu,0x92722c85u,
            0xa2bfe8a1u,0xa81a664bu,0xc24b8b70u,0xc76c51a3u,0xd192e819u,0xd6990624u,0xf40e3585u,0x106aa070u,
            0x19a4c116u,0x1e376c08u,0x2748774cu,0x34b0bcb5u,0x391c0cb3u,0x4ed8aa4au,0x5b9cca4fu,0x682e6ff3u,
            0x748f82eeu,0x78a5636fu,0x84c87814u,0x8cc70208u,0x90befffau,0xa4506cebu,0xbef9a3f7u,0xc67178f2u};
        uint32_t w[64]{};
        for (unsigned i=0;i<16;++i)
            w[i]=(uint32_t(block_[4*i])<<24)|(uint32_t(block_[4*i+1])<<16)|
                 (uint32_t(block_[4*i+2])<<8)|uint32_t(block_[4*i+3]);
        for (unsigned i=16;i<64;++i)
        {
            const uint32_t s0=rotate(w[i-15],7)^rotate(w[i-15],18)^(w[i-15]>>3);
            const uint32_t s1=rotate(w[i-2],17)^rotate(w[i-2],19)^(w[i-2]>>10);
            w[i]=w[i-16]+s0+w[i-7]+s1;
        }
        uint32_t a=state_[0],b=state_[1],c=state_[2],d=state_[3],e=state_[4],f=state_[5],g=state_[6],h=state_[7];
        for (unsigned i=0;i<64;++i)
        {
            const uint32_t s1=rotate(e,6)^rotate(e,11)^rotate(e,25);
            const uint32_t t1=h+s1+((e&f)^(~e&g))+k[i]+w[i];
            const uint32_t s0=rotate(a,2)^rotate(a,13)^rotate(a,22);
            const uint32_t t2=s0+((a&b)^(a&c)^(b&c));
            h=g;g=f;f=e;e=d+t1;d=c;c=b;b=a;a=t1+t2;
        }
        state_[0]+=a;state_[1]+=b;state_[2]+=c;state_[3]+=d;
        state_[4]+=e;state_[5]+=f;state_[6]+=g;state_[7]+=h;
    }
public:
    void update(const unsigned char *data, size_t count)
    {
        if (count > std::numeric_limits<uint64_t>::max()/8-bytes_)
            throw std::runtime_error("SHA256 input exceeds64-bit bit-length bound");
        bytes_ += count;
        while (count)
        {
            const size_t n = count < block_.size()-used_ ? count : block_.size()-used_;
            std::memcpy(block_.data()+used_,data,n);used_+=n;data+=n;count-=n;
            if (used_==block_.size()) { compress();used_=0; }
        }
    }
    std::string finish()
    {
        const uint64_t bits=bytes_*8;
        block_[used_++]=0x80;
        if (used_>56)
        {
            while (used_<64) block_[used_++]=0;
            compress();used_=0;
        }
        while (used_<56) block_[used_++]=0;
        for (unsigned i=0;i<8;++i) block_[56+i]=static_cast<unsigned char>(bits>>(56-8*i));
        compress();
        static const char hex[]="0123456789abcdef";
        std::string out;out.reserve(64);
        for (uint32_t value:state_)
            for (int shift=28;shift>=0;shift-=4) out+=hex[(value>>shift)&15];
        return out;
    }
};
}

bool FileSnapshot::operator==(const FileSnapshot &o) const
{
    return device==o.device && inode==o.inode && size==o.size &&
           mtime_seconds==o.mtime_seconds && mtime_nanoseconds==o.mtime_nanoseconds &&
           ctime_seconds==o.ctime_seconds && ctime_nanoseconds==o.ctime_nanoseconds;
}
FileSnapshot snapshotFile(const std::string &path)
{
    Descriptor file(path);
    const FileSnapshot before=descriptorSnapshot(file);
    if (before!=pathnameSnapshot(path)) throw error(path,"pathname changed during snapshot");
    file.closeChecked();
    return before;
}
FileDigest digestFile(const std::string &path)
{
    Descriptor file(path);
    const FileSnapshot before=descriptorSnapshot(file);
    Sha256 sha;
    std::array<unsigned char,64*1024> buffer{};
    uint64_t count=0;
    for (;;)
    {
        ssize_t n;
        do { n=::read(file.fd,buffer.data(),buffer.size()); } while (n<0 && errno==EINTR);
        if (n<0) throw error(path,"read: "+std::string(std::strerror(errno)));
        if (n==0) break;
        if (static_cast<uint64_t>(n)>before.size-count) throw error(path,"grew while reading");
        count+=static_cast<uint64_t>(n);
        try { sha.update(buffer.data(),static_cast<size_t>(n)); }
        catch (const std::exception &e) { throw error(path,e.what()); }
    }
    if (count!=before.size || descriptorSnapshot(file)!=before || pathnameSnapshot(path)!=before)
        throw error(path,"size/descriptor/path changed while reading");
    file.closeChecked();
    return {sha.finish(),before};
}
void requireUnchanged(const std::string &path, const FileSnapshot &snapshot)
{
    if (snapshotFile(path)!=snapshot) throw error(path,"changed since processing snapshot");
}
std::string sha256Bytes(const void *data, size_t count)
{
    if (!data && count) throw std::runtime_error("SHA256 nonzero input has null pointer");
    Sha256 sha;sha.update(static_cast<const unsigned char *>(data),count);return sha.finish();
}
std::string executablePath()
{
#ifdef __linux__
    const std::string path="/proc/self/exe";
    snapshotFile(path); // Require actual running executable identity, not a guess.
    return path;
#elif defined(__APPLE__)
    uint32_t size=0;
    (void)_NSGetExecutablePath(nullptr,&size);
    if (!size) throw error("<running executable>","loader path unavailable");
    std::vector<char> buffer(size);
    if (_NSGetExecutablePath(buffer.data(),&size)!=0) throw error("<running executable>","loader path changed");
    char *canonical=::realpath(buffer.data(),nullptr);
    if (!canonical) throw error(buffer.data(),"realpath: "+std::string(std::strerror(errno)));
    const std::string path(canonical);std::free(canonical);
    snapshotFile(path);return path;
#else
    throw error("<running executable>","unsupported executable identity platform");
#endif
}
}
