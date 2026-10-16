#include <cstdio>
#include <cstring>
int main(int argc,char **argv) {
 bool correct=argc>1 && !strcmp(argv[1],"pclose");
 int failures=0;
 for(int n=0;n<5;++n) {
  FILE *p=popen("printf test", "r");
  char b[5]={}; size_t count=p?fread(b,1,4,p):0;
  int result=p?(correct?pclose(p):fclose(p)):-1;
  printf("iteration=%d bytes=%zu close=%d\n",n,count,result);
  failures+=count!=4;
 }
 return failures?1:0;
}
