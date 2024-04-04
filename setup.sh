sed -i 's/ports.ubuntu.com/mirrors.ustc.edu.cn/g' /etc/apt/sources.list
sed -i 's/mirrors.tuna.tsinghua.edu.cn/mirrors.ustc.edu.cn/g' /etc/apt/sources.list


apt update
apt install brotli cpio android-sdk-libsparse-utils e2fsprogs -y