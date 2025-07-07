#	perl file_scrambler.pl 	dir 	string8digit_HEX
#	doesnt work completely on text/CSV and binary files. 
#
#  perl file_scrambler.pl folder_path code_to_scramble
#			
#
#
#
#
#


use strict;
my $dir= $ARGV[0];
my $h= $ARGV[1];
my @files = file_list("$dir");


sub file_list
{
	my $root_dir_name = shift;
	my $filename;
	my @filelist;
	opendir ( DIR, $root_dir_name ) || die "Error in opening dir $root_dir_name\n";
	while( ($filename = readdir(DIR)))
	{
		if( -f "$root_dir_name/$filename")
		{
			push (@filelist, $filename);
			
		}
	}
	closedir(DIR);
	return @filelist;

}
foreach(@files){

encode_file("$dir\\$_", $h);

}


sub encode_file
{
my $infile= shift;
my $code = hex shift;
my $outfile = $infile."t";
open (OUTFILE, ">", $outfile) or die "Not able to open the file for writing. \n";
binmode (OUTFILE);
open INFILE, $infile or die $!;
binmode INFILE;
print "processing $infile.....     ";
my $i = 0;
my ($buf, $data, $n);
while (($n = read INFILE, $data, 4) != 0) {
if($i<50){
	$i++;
 my $binary = unpack('B*', $data);
 my $dec= bin2dec($binary);
 my $dec2 = $dec^$code;
 my $binaryout = dec2bin($dec2,);
 print OUTFILE pack('B*', $binaryout);
}else{
print OUTFILE $data;}
}
print "DONE\n";
close(INFILE);
close (OUTFILE);
unlink ($infile);
rename( $outfile, $infile);
}




sub bin2dec {
    return unpack("N", pack("B32", substr("0" x 32 . shift, -32)));
}


sub dec2bin {
	my $x = shift;
	my $ny = shift;
	my $n = $ny*8;
	
    my $str = unpack("B32", pack("N", $x));
    return $str;
}
