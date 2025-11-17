#include "UuidGeneration.h"

uuids::uuid generateRandomUuid()
{
    std::mt19937 rng{std::random_device{}()};     
    uuids::uuid_random_generator generator(rng);
    return generator();
}